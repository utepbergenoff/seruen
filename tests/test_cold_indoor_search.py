"""Shelter is a hard constraint before ranking/Gemini, including the user's exact report."""
import copy
import json
from datetime import datetime

import pytest
from fastapi.testclient import TestClient

from backend.app import create_app
from backend.discovery import search_intent, to_poi
from backend.feature_data import apply_feedback
from backend.geo import ALMATY
from backend.indoor import shelter_requested
from backend.intent import rule_intent
from backend.loader import Dataset
from backend.retrieval import Retriever
from backend.schemas import Draft, Generated, POI, RecommendRequest
from test_discovery import place, transport

QUERY = "я с ребенком. На улице холодно. Куда пойти?"
ASK = {
    "location": {"lat": 51.128, "lon": 71.430},
    "query": QUERY, "finish_mode": "place",
    "context": {"now": "2026-10-20T14:00:00+05:00", "simulate": True, "time_budget_min": 60,
                "companions": "alone", "weather": {"temp_c": 4, "wind_ms": 3}},
}


@pytest.mark.parametrize("query", [
    QUERY, "Замёрзли. Где погреться?", "Хочу согреться", "Нам холодно, куда сходить с детьми?",
    "Хочу погулять с ребенком, на улице мороз", "Не хочу мерзнуть, куда пойти?",
    "Нужна крытая игровая площадка", "Хочу в помещении",
    "Холодно, и мы не хотим гулять на улице", "Cold, but we don't want to go outside",
    "I'm with my child. It's cold outside. Where can we go?", "We are freezing, somewhere warm please",
    "Баламен жүрмін. Далада суық. Қайда баруға болады?", "Тоңдық, қайда жылынуға болады?",
])
def test_text_shelter_survives_mild_weather_and_keeps_original_request(query):
    req = RecommendRequest.model_validate({**ASK, "query": query})
    normalized = apply_feedback(req)
    assert normalized.preferences.indoor_only
    assert not req.preferences.indoor_only
    assert normalized.context.weather == req.context.weather  # do not manufacture a cold forecast
    intent, catalog_query = search_intent(normalized)
    assert intent.relevant and "outdoor_walk" not in intent.tags
    assert "park" not in intent.categories and catalog_query != query


@pytest.mark.parametrize("query", [
    "С ребенком, не холодно, хочу в парк", "Я не замёрз, хочу гулять в парке",
    "Хочу холодный кофе", "I want cold brew coffee", "It's not cold, walk in the park",
    "It isn't cold outside, a walk please", "Дала суық емес, саябақта серуен",
    "Холодно, но хотим гулять на улице", "It is cold, but we still want to walk outdoors",
])
def test_negation_drinks_and_explicit_outdoor_choice_are_not_shelter(query):
    assert not shelter_requested(query)
    req = RecommendRequest.model_validate({**ASK, "query": query})
    assert not apply_feedback(req).preferences.indoor_only
    req.preferences.indoor_only = True
    assert apply_feedback(req).preferences.indoor_only  # explicit settings are never weakened


@pytest.mark.parametrize("query", ["Куда пойти в помещении?", "Somewhere indoors please"])
def test_generic_indoor_request_does_not_search_only_landmarks(query):
    req = RecommendRequest.model_validate({**ASK, "query": query})
    intent, catalog_query = search_intent(req)
    assert "coffee" in intent.categories and "shopping" in intent.categories
    assert catalog_query == "Кофейни"


def local_pois():
    return [
        POI(poi_id="outside_playground", name="SYNTHETIC Детская площадка", lat=51.128, lon=71.430,
            category="kids", indoor=False, kid_friendly=True, popularity=1),
        POI(poi_id="indoor_center", name="SYNTHETIC Детский игровой центр", lat=51.129, lon=71.430,
            category="kids", indoor=True, kid_friendly=True),
        POI(poi_id="unknown_center", name="SYNTHETIC Детский клуб", lat=51.128, lon=71.430,
            category="kids", indoor=False, kid_friendly=True),
        POI(poi_id="closed_center", name="SYNTHETIC Закрытый игровой центр", lat=51.128, lon=71.430,
            category="kids", indoor=True, kid_friendly=True, hours_source="osm", opening_hours_raw="Mo-Su 18:00-20:00"),
        POI(poi_id="adults_only", name="SYNTHETIC Только взрослым", lat=51.128, lon=71.430,
            category="kids", indoor=True, kid_friendly=False, adult_only=True),
    ]


def test_raw_retriever_never_ranks_an_outdoor_or_unknown_place_above_indoor(settings):
    req = RecommendRequest.model_validate(ASK)
    result = Retriever(Dataset(local_pois(), "synthetic", 0, 0), None).search(
        req, rule_intent(req), datetime(2026, 10, 20, 14, tzinfo=ALMATY))
    assert [h.poi.poi_id for h in result.hits] == ["indoor_center"]
    excluded = {p.poi_id: p.excluded_because for p in result.excluded}
    assert excluded["outside_playground"] == excluded["unknown_center"] == "indoor_required"
    assert excluded["closed_center"] == "closed" and excluded["adults_only"] == "not_child_friendly"


@pytest.fixture
def local(settings, tmp_path):
    settings.poi_path = tmp_path / "synthetic_pois.json"
    settings.poi_path.write_text(json.dumps([p.model_dump(mode="json") for p in local_pois()]), encoding="utf-8")
    settings.index_path = None
    return settings


@pytest.mark.parametrize("source", ["local", "auto"])
def test_api_filters_local_and_failed_provider_fallback_and_keeps_it_in_plan(local, source):
    local.twogis_enabled, local.twogis_api_key = True, "synthetic-key"
    with TestClient(create_app(local, twogis_transport=transport(code=403))) as c:
        req = {**copy.deepcopy(ASK), "source": source}
        r = c.post("/recommend", json=req)
        assert r.status_code == 200
        d = r.json()
        assert [p["poi_id"] for p in d["recommendations"]] == ["indoor_center"]
        assert d["applied_preferences"]["indoor_only"] and d["considered"]["companions"] == "child"
        assert "В помещении" in d["considered"]["filters"]
        assert "В помещении" in d["recommendations"][0]["why"]
        if source == "auto":
            assert d["source"] == "local" and d["source_error"] == "twogis_access_denied"
        built = c.post("/plans/build", json={"request": {**req, "source": "local"},
                       "stop_ids": ["indoor_center"], "finish_mode": "destination",
                       "finish_poi_id": "indoor_center", "destination": {"lat": 51.129, "lon": 71.430}}).json()
        assert built["fits"] and built["applied_preferences"]["indoor_only"]


def test_no_indoor_options_is_honest_and_cannot_relax_back_to_playgrounds(local):
    local.poi_path.write_text(json.dumps([local_pois()[0].model_dump(mode="json")]), encoding="utf-8")
    with TestClient(create_app(local)) as c:
        d = c.post("/recommend", json={**ASK, "source": "local"}).json()
        assert d["recommendations"] == []
        assert d["applied_preferences"]["indoor_only"]
        assert "allow_outdoor" not in d["relaxation_options"]
        assert any("Подходящие помещения рядом не найдены" in note for note in d["notes"])


@pytest.mark.parametrize("rubric,attributes,expected", [
    ("Детские игровые площадки", [], False),
    ("Детские / подростковые клубы", [], False),
    ("Детские развлекательные центры", [], True),
    ("Детские игровые центры", [], True),
    ("Детские игровые залы / Игротеки", [], True),
    ("Детские игровые комнаты", [], True),
    ("Детские развлекательные центры", ["На открытом воздухе"], False),
    ("Музеи", [], True),
    ("Музеи под открытым небом", [], False),
])
def test_provider_indoor_classification_uses_rubrics_not_the_name(rubric, attributes, expected):
    raw = place(name="SYNTHETIC Тёплое место", rubrics=[{"name": rubric}],
                attribute_groups=[{"attributes": [{"name": x} for x in attributes]}])
    poi = to_poi(raw, RecommendRequest.model_validate(ASK), 1500)
    assert poi.indoor is expected


class CaptureCandidates:
    def __init__(self):
        self.calls = []

    async def generate(self, request, intent, hits):
        self.calls.append((request, hits))
        assert request.preferences.indoor_only
        assert all(h.poi.indoor and h.poi.kid_friendly for h in hits)
        return Generated(recommendations=[
            Draft(poi_id=h.poi.poi_id, why="В помещении, подходит для посещения с ребёнком.",
                  what_to_do="Уточните возрастные ограничения и условия входа.",
                  time_to_spend_min=h.stay, evidence_ids=["indoor", "child_friendly"]) for h in hits
        ])


@pytest.mark.parametrize("source", ["local", "2gis"])
def test_gemini_only_receives_indoor_child_candidates_and_map_does_not_reintroduce_playgrounds(local, source):
    local.twogis_enabled, local.twogis_api_key, local.gemini_api_key = True, "synthetic-key", "synthetic-gemini"
    provider = CaptureCandidates()
    seen = []
    items = [
        place(1, name="SYNTHETIC Outdoor", rubrics=[{"name": "Детские игровые площадки"}]),
        place(2, name="SYNTHETIC Indoor", rubrics=[{"name": "Детские развлекательные центры"}]),
        place(3, name="SYNTHETIC Unknown", rubrics=[{"name": "Детские / подростковые клубы"}]),
    ]
    with TestClient(create_app(local, provider=provider, twogis_transport=transport(items, seen=seen))) as c:
        d = c.post("/recommend", json={**ASK, "source": source}).json()
        assert len(provider.calls) == 1
        assert len(d["recommendations"]) == 1 and d["recommendations"][0]["why_source"] == "ai"
        if source == "2gis":
            assert seen[0].url.params["q"] == "Детские развлекательные центры"
            assert [p["name"] for p in d["nearby_places"]] == ["SYNTHETIC Indoor"]
