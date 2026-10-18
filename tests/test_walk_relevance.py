"""Activity relevance regressions from the published Mega Silk Way scenario."""
import pytest

from backend.activities import activity, outdoor_walk_place
from backend.config import ROOT, Settings
from backend.fallback import drafts
from backend.intent import rule_intent
from backend.loader import Dataset
from backend.retrieval import Retriever
from backend.schemas import POI, RecommendRequest
from backend.service import RecommendationService


def request(query):
    return RecommendRequest(location={"lat": 51.089, "lon": 71.407}, query=query, source="local",
                            context={"time_budget_min": 60, "now": "2026-10-18T17:30:00+05:00", "simulate": True})


@pytest.mark.parametrize("query", ["Хочу прогуляться 30–60 минут", "Walk near Mega Silk Way",
                                   "Бір сағат серуендегім келеді", "Парк рядом"])
async def test_real_mega_walk_recommends_outdoor_places_not_chaplin(query):
    service = RecommendationService(Settings(poi_path=ROOT / "data/poi.json", data_kind="real", warm_cache=False))
    assert service.retriever.mode == "bm25+lsa", "Reindex the shipped real dataset before accepting retrieval"
    req = request(query)
    answer, _ = await service.recommend(req, force_no_ai=True)
    assert 1 <= len(answer.recommendations) <= 3
    assert "outdoor_walk" not in answer.considered.filters  # internal marker has no UI label
    by_id = {p.poi_id: p for p in service.dataset.pois}
    assert all(outdoor_walk_place(by_id[c.poi_id]) for c in answer.recommendations)
    assert all("Chaplin" not in c.name for c in answer.recommendations)


def test_walk_constraint_survives_category_relaxation_and_generated_descriptions(settings):
    service = RecommendationService(settings)
    cinema = POI(poi_id="cinema", name="Chaplin Cinema", category="culture", lat=51.089, lon=71.407,
                 description="Прогулка, памятник, сквер", description_source="generated")
    service.retriever = Retriever(Dataset([cinema], "synthetic", 0, 0), None)
    assert activity(cinema) == "cinema" and not outdoor_walk_place(cinema)
    assert not service.inspect(request("Хочу прогуляться"))[2].hits
    # Even without an indoor flag, provider/name evidence establishes a cinema.
    req = request("Хочу в кинотеатр")
    intent, _, search = service.inspect(req)
    assert search.hits
    action = drafts(search.hits, intent)[0].what_to_do
    assert "сеанс" in action and "экспозици" not in action


@pytest.mark.parametrize("query", ["Walk to a museum", "Прогуляться до кинотеатра", "Мұражайға барғым келеді"])
def test_explicit_indoor_visit_is_not_overridden_by_walk(query):
    intent = rule_intent(request(query))
    assert intent.relevant and intent.categories == ["culture"]
    assert "outdoor_walk" not in intent.tags


def test_unknown_culture_does_not_invent_an_exhibition(settings):
    service = RecommendationService(settings)
    poi = POI(poi_id="c", name="Культурный центр", category="culture", lat=51.089, lon=71.407)
    service.retriever = Retriever(Dataset([poi], "synthetic", 0, 0), None)
    intent, _, search = service.inspect(request("Необычное рядом"))
    assert "экспозици" not in drafts(search.hits, intent)[0].what_to_do
