import asyncio
import json
from datetime import datetime

import httpx
import pytest

from backend.app import scenarios
from backend.config import ROOT
from backend.generate import AIError, Gemini
from backend.geo import ALMATY
from backend.intent import rule_intent
from backend.retrieval import Retriever
from backend.schemas import Draft, Generated, RecommendRequest
from backend.service import RecommendationService


def test_dedupe_same_place_once(service):
    assert service.dataset.duplicates == 2 and service.dataset.rejected == 2
    assert len(service.dataset.pois) == 24


def test_no_internet_bm25_fallback(service, settings, tmp_path, req):
    retriever = Retriever(service.dataset, tmp_path / "missing.json")
    assert retriever.mode == "bm25"
    result = retriever.search(req, rule_intent(req), datetime(2026, 10, 18, 14, tzinfo=ALMATY))
    assert result.hits


def test_hybrid_index_and_stale_rejection(service, settings, tmp_path):
    assert service.retriever.mode == "bm25+lsa"
    data = json.loads(settings.index_path.read_text(encoding="utf-8"))
    data["fingerprint"] = "wrong"
    path = tmp_path / "index.json"
    path.write_text(json.dumps(data), encoding="utf-8")
    assert Retriever(service.dataset, path).mode == "bm25"


async def test_fr9_empty_radius_expands_without_overbudget(service, req):
    # A single eligible point ~956m away: outside 865m, inside expanded radius.
    p = service.dataset.pois[3].model_copy(update={"lat": 51.0976, "lon": 71.417, "category": "park"})
    service.dataset.pois = [p]
    service.retriever = Retriever(service.dataset, ROOT / "data/index/missing.json")
    req.query = "прогулка"
    req.context.time_budget_min = 60
    response, _ = await service.recommend(req)
    assert response.considered.radius_expanded
    assert response.recommendations
    assert response.recommendations[0].budget_breakdown.total_min <= 60


async def test_unknown_hours_note(service, req):
    service.dataset.pois = [p for p in service.dataset.pois if p.poi_id == "sample_023"]
    service.retriever = Retriever(service.dataset, ROOT / "missing.json")
    response, _ = await service.recommend(req)
    assert response.recommendations[0].open_status.state == "unknown"
    assert any("неизвестны" in n for n in response.notes)
    assert "открыто" not in response.recommendations[0].why.lower()


def test_unverified_event_is_excluded(service, req):
    req.query = "Необычное"
    _, _, result = service.inspect(req)
    assert any(c.poi_id == "sample_024" and c.excluded_because == "event_unverified" for c in result.excluded)


async def test_weather_prioritizes_indoor_and_short_walks(service, req):
    from backend.schemas import Weather

    req.context.weather = Weather(temp_c=-20, wind_ms=12)
    response, _ = await service.recommend(req)
    assert response.safety and response.considered.radius_m <= 500
    assert all(r.distance_m <= 500 for r in response.recommendations)


async def test_cache_hit_context_and_privacy(service, req):
    first, _ = await service.recommend(req)
    second, _ = await service.recommend(req)
    assert first.mode == "no_ai" and second.mode == "cached"
    serialized = str(service.cache.entries)
    assert req.query not in serialized
    assert all(len(k) == 64 for k in service.cache.entries)
    req.context.companions = "child"
    changed, _ = await service.recommend(req)
    assert changed.mode == "no_ai"


async def test_cache_rechecks_closing_inside_slot(service, req):
    p = service.dataset.pois[0].model_copy(update={"opening_hours_raw": "Mo-Su 08:00-14:10"})
    service.dataset.pois = [p]
    service.retriever = Retriever(service.dataset, ROOT / "missing.json")
    req.context.now = datetime(2026, 10, 18, 14, 5, tzinfo=ALMATY)
    first, _ = await service.recommend(req)
    assert first.recommendations
    req.context.now = datetime(2026, 10, 18, 14, 15, tzinfo=ALMATY)
    second, _ = await service.recommend(req)
    assert not second.recommendations and second.mode != "cached"


async def test_cache_lru_size(service, req):
    service.cache.size = 2
    for q in ["кофе", "прогулка", "музей"]:
        req.query = q
        await service.recommend(req)
    assert len(service.cache.entries) == 2


class FakeGemini:
    def __init__(self, behavior):
        self.behavior = behavior

    async def intent(self, request, rules):
        if self.behavior == "timeout":
            await asyncio.sleep(1)
        if self.behavior == "error":
            raise RuntimeError("private secret provider message")
        return rules

    async def generate(self, request, intent, hits):
        d = Draft(
            poi_id=hits[0].poi.poi_id,
            why="Подходит по категории.",
            time_to_spend_min=480,
            what_to_do="Осмотрите общедоступную территорию.",
        )
        if self.behavior == "invent":
            return Generated(recommendations=[d.model_copy(update={"poi_id": "invented_999"}), d])
        if self.behavior == "open":
            d.why = "Сейчас открыто, приходите."
        if self.behavior == "long":
            d.why = "слово " * 30
        return Generated(recommendations=[d])


@pytest.mark.parametrize("behavior", ["error", "timeout", "open", "long"])
async def test_ai_failure_falls_back(settings, req, behavior):
    settings.gemini_api_key = "synthetic-test-key"
    settings.ai_timeout_s = 0.02
    service = RecommendationService(settings, FakeGemini(behavior))
    response, error = await service.recommend(req)
    assert response.mode == "no_ai" and response.recommendations
    assert error == "ai_unavailable"


async def test_no_invented_ids_and_clamped_budget(settings, req):
    settings.gemini_api_key = "synthetic-test-key"
    service = RecommendationService(settings, FakeGemini("invent"))
    response, error = await service.recommend(req)
    assert response.mode == "ai"
    assert all(r.poi_id != "invented_999" for r in response.recommendations)
    assert service.metrics["invented_ids_rejected"] == 1
    assert error == "invented_id_rejected"
    assert all(r.budget_breakdown.total_min <= 120 for r in response.recommendations)
    assert all(r.time_to_spend_min <= 78 for r in response.recommendations)


async def test_single_ai_pick_is_filled_up_to_three_with_honest_sources(settings, req):
    settings.gemini_api_key = "synthetic-test-key"
    service = RecommendationService(settings, FakeGemini("one"))
    response, error = await service.recommend(req)
    _, _, search = service.inspect(req)
    recs = response.recommendations
    assert response.mode == "ai" and error == "none"
    assert len(recs) == min(3, len(search.hits)) >= 2
    assert recs[0].poi_id == search.hits[0].poi.poi_id
    assert recs[0].why_source == recs[0].what_to_do_source == "ai"
    assert all(r.why_source == r.what_to_do_source == "template" for r in recs[1:])
    assert len({r.poi_id for r in recs}) == len(recs)
    assert {r.poi_id for r in recs} <= {h.poi.poi_id for h in search.hits}


async def test_real_http_adapter_schema_and_key_header(settings, req):
    settings.gemini_api_key = "synthetic-test-key"

    def handler(request):
        assert request.headers["x-goog-api-key"] == "synthetic-test-key"
        assert "key=" not in str(request.url)
        body = json.loads(request.content)
        assert body["generationConfig"]["responseMimeType"] == "application/json"
        assert "responseJsonSchema" in body["generationConfig"]
        return httpx.Response(
            200,
            json={
                "candidates": [
                    {"finishReason": "STOP", "content": {"parts": [{"text": rule_intent(req).model_dump_json()}]}}
                ]
            },
        )

    provider = Gemini(settings, httpx.MockTransport(handler))
    assert await provider.intent(req, rule_intent(req)) == rule_intent(req)


@pytest.mark.parametrize("kind", ["http", "invalid_json", "incomplete"])
async def test_http_adapter_errors(settings, kind):
    settings.gemini_api_key = "synthetic-test-key"

    def handler(request):
        if kind == "http":
            return httpx.Response(429, text="sensitive provider content")
        if kind == "invalid_json":
            return httpx.Response(200, text="invalid")
        return httpx.Response(200, json={"candidates": [{"finishReason": "MAX_TOKENS"}]})

    with pytest.raises(AIError):
        await Gemini(settings, httpx.MockTransport(handler)).structured("system", {}, {})


async def test_30_intents_match_expected(service):
    cases = json.loads((ROOT / "eval/scenarios.json").read_text(encoding="utf-8"))["cases"]
    correct = 0
    for row in cases:
        intent = rule_intent(RecommendRequest.model_validate(row["request"])).model_dump()
        correct += all(intent[k] == v for k, v in row["expected_intent"].items())
    assert correct / len(cases) >= 0.9, (correct, len(cases))


@pytest.mark.parametrize("row", scenarios(), ids=lambda s: s["id"])
async def test_fr4_budgets_include_return_and_reserve(service, row):
    response, _ = await service.recommend(RecommendRequest.model_validate(row["request"]), use_cache=False)
    for rec in response.recommendations:
        b = rec.budget_breakdown
        assert b.total_min == b.walk_there_min + b.walk_back_min + b.stay_min + b.reserve_min
        assert b.walk_there_min == b.walk_back_min == rec.walk_min
        assert b.total_min <= row["request"]["context"]["time_budget_min"]
