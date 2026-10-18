import json
from datetime import datetime

import pytest

from backend.app import create_app, scenarios
from backend.config import ROOT, Settings
from backend.embeddings import build_index
from backend.geo import ALMATY
from backend.hours import open_status
from backend.loader import load_pois
from backend.schemas import RecommendRequest
from backend.service import RecommendationService


@pytest.fixture(scope="module")
def real_service(tmp_path_factory):
    index = tmp_path_factory.mktemp("real_index") / "lsa.json"
    settings = Settings(poi_path=ROOT / "data/poi.json", index_path=index, data_kind="real", warm_cache=False)
    build_index(load_pois(settings.poi_path), index)
    return RecommendationService(settings)


def test_named_neighbours_categories_and_generic_objects_are_preserved(tmp_path):
    base = load_pois(ROOT / "data/poi_sample.json").pois[0].model_dump(mode="json")
    rows = [
        {**base, "poi_id": "g1", "name": "Сквер", "name_generic": True},
        {**base, "poi_id": "g2", "name": "Сквер", "name_generic": True},
        {**base, "poi_id": "n1", "name": "Mega", "category": "shopping"},
        {**base, "poi_id": "n2", "name": "Mega", "category": "coffee"},
        {**base, "poi_id": "n3", "name": "Mega", "category": "coffee", "lat": base["lat"] + 0.0005},
        {**base, "poi_id": "dup", "name": "Mega", "category": "coffee"},
    ]
    path = tmp_path / "pois.json"
    path.write_text(json.dumps(rows), encoding="utf-8")
    result = load_pois(path)
    assert {p.poi_id for p in result.pois} == {"g1", "g2", "n1", "n2", "n3"}
    assert result.duplicates == 1 and result.rejected == 0


def test_snapshot_metadata_survives_contract_export(real_service):
    assert len(real_service.dataset.pois) == 1251
    assert real_service.retriever.mode == "bm25+lsa"
    assert sum(p.name_generic for p in real_service.dataset.pois) == 418
    assert sum(bool(p.google_place_id) for p in real_service.dataset.pois) == 125
    assert sum(bool(p.description_url) for p in real_service.dataset.pois) == 22


@pytest.mark.parametrize("scenario", scenarios(), ids=lambda s: s["id"])
async def test_real_demo_invariants(real_service, scenario):
    request = RecommendRequest.model_validate(scenario["request"])
    result, error = await real_service.recommend(request, use_cache=False)
    assert error == "none" and result.data_kind == "real"
    assert result.considered.retrieval_mode == "bm25+lsa"
    assert result.recommendations or result.notes  # honest empty result is allowed for sparse areas
    ids = {p.poi_id for p in real_service.dataset.pois}
    for card in result.recommendations:
        assert card.poi_id in ids and card.budget_breakdown.total_min <= result.considered.time_budget_min
        assert card.open_status.state != "closed"
    assert any("Демо-расчёт" in note for note in result.notes)


@pytest.mark.parametrize("scenario_id", ["S2", "S4"])
@pytest.mark.parametrize("simulate", [False, True])
async def test_night_safety_at_same_time_for_child_and_unusual(real_service, scenario_id, simulate):
    request = RecommendRequest.model_validate(next(s["request"] for s in scenarios() if s["id"] == scenario_id))
    at = datetime(2026, 10, 18, 1, 4, tzinfo=ALMATY)
    request.context.simulate = simulate
    request.context.now = at
    result, _ = await real_service.recommend(request, use_cache=False, current=at)
    assert result.safety and any("Ночью" in note for note in result.safety)
    assert result.considered.radius_m <= 1000
    assert result.considered.target_time == at
    by_id = {p.poi_id: p for p in real_service.dataset.pois}
    assert all(
        by_id[c.poi_id].indoor or {"lit", "busy", "освещено", "людно"} & set(by_id[c.poi_id].tags)
        for c in result.recommendations
    )


async def test_day_simulation_does_not_claim_current_night(real_service):
    request = RecommendRequest.model_validate(scenarios()[1]["request"])
    result, _ = await real_service.recommend(
        request, use_cache=False, current=datetime(2026, 10, 18, 1, 4, tzinfo=ALMATY)
    )
    assert result.considered.target_time.hour == 14
    assert not result.safety
    assert any("14:00" in note and "Демо-расчёт" in note for note in result.notes)


def test_real_parks_24h_are_schedule_claims_and_unlit_parks_excluded_at_night(real_service):
    now = datetime(2026, 10, 18, 1, 0, tzinfo=ALMATY)
    parks = [p for p in real_service.dataset.pois if p.category == "park"]
    always = [p for p in parks if p.opening_hours_raw == "24/7"]
    assert len(always) == 2
    for park in always:
        status = open_status(park, now)
        assert status.state == "open" and status.source == "osm" and status.hours == "24/7"
        request = RecommendRequest(location={"lat": park.lat, "lon": park.lon}, query="Прогулка рядом")
        _, _, found = real_service.inspect(request, current=now)
        assert park.poi_id not in {h.poi.poi_id for h in found.hits}
        assert any(c.poi_id == park.poi_id and c.excluded_because == "night_safety_unconfirmed" for c in found.excluded)


def test_public_scenarios_label_matches_real_dataset(real_service):
    from fastapi.testclient import TestClient

    with TestClient(create_app(real_service.settings)) as client:
        assert all(s["data_kind"] == "real" for s in client.get("/scenarios").json())


async def test_inferred_sockets_are_qualified_in_template(real_service):
    poi = next(p for p in real_service.dataset.pois if p.category == "library" and "розетки" in p.tags_inferred)
    request = RecommendRequest(
        location={"lat": poi.lat, "lon": poi.lon},
        query="Тихо, розетки",
        context={
            "simulate": True,
            "now": "2026-10-18T14:00:00+05:00",
            "time_budget_min": 120,
        },
    )
    result, _ = await real_service.recommend(request, use_cache=False)
    for card in result.recommendations:
        if card.poi_id == poi.poi_id:
            assert "Обычно" in card.why and "уточните" in card.why
            break
    else:
        pytest.fail("Nearby matching library missing")


async def test_work_places_are_within_fifteen_minutes(real_service):
    result, _ = await real_service.recommend(
        RecommendRequest.model_validate(scenarios()[0]["request"]), use_cache=False
    )
    assert result.recommendations
    assert all(card.walk_min <= 15 for card in result.recommendations)


async def test_sightseeing_before_flight_is_not_a_playground_or_mall(real_service):
    request = RecommendRequest(
        location={"lat": 51.111, "lon": 71.526},
        query="2 часа перед вылетом, что посмотреть?",
        context={"time_budget_min": 120, "simulate": True, "now": "2026-10-18T16:00:00+05:00"},
    )
    result, _ = await real_service.recommend(request, use_cache=False)
    assert result.recommendations
    assert all(c.category in {"viewpoint", "culture", "park", "coffee", "unusual"} for c in result.recommendations)
    assert all(c.budget_breakdown.reserve_min == 60 for c in result.recommendations)
