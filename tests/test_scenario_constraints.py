"""Cross-scenario regressions. All venue facts in this file are synthetic."""
import json
from datetime import datetime, timedelta
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from backend.app import create_app
from backend.discovery import to_poi
from backend.feature_data import apply_feedback
from backend.hours import closed_during_visit
from backend.indoor import indoor_required
from backend.intent import rule_intent
from backend.loader import Dataset
from backend.query_constraints import expense_mode, spending_limit, time_limit
from backend.retrieval import Retriever
from backend.schemas import POI, RecommendRequest, Weather
from test_discovery import place, transport
from test_feature_expansion import expanded as expanded, api as api, ASK, post


@pytest.mark.parametrize("query,minutes", [
    ("Есть 20 минут, куда сходить?", 20), ("Хочу погулять полтора часа", 90),
    ("I have one and a half hours to walk", 90), ("Бір жарым сағат серуен", 90),
    ("Хочу погулять 1,5 часа", 90), ("Хочу погулять 1.5 hours", 90),
    ("Есть 1 час 30 минут", 90), ("1 hour 30 minutes", 90),
    ("Есть 30 минут, кофе в 5 минутах пешком", 30),
    ("Есть 20 минут, до места идти 10 минут", 20),
    ("Гуляли 10 минут, осталось 20 минут", 20),
    ("Рабочие часы кофейни", None), ("Кофе до 2000 тенге", None),
    ("30–60 минут", 60), ("полчаса-час", 60), ("a walk for half an hour", 30),
])
def test_explicit_time_limits(query, minutes):
    assert time_limit(query) == minutes


@pytest.mark.parametrize("context,text,expected", [(120, 20, 20), (15, 60, 15), (None, 30, 30)])
def test_shorter_time_limit_wins_over_stale_slider(context, text, expected):
    req = RecommendRequest.model_validate({**ASK, "query": f"Хочу кофе, есть {text} минут",
        "context": {**ASK["context"], "time_budget_min": context}})
    assert rule_intent(req).time_budget_min == expected


@pytest.mark.parametrize("query,child,categories", [
    ("Я с детьми, хочу кофе", True, ["coffee", "library", "cowork"]),
    ("Я с ребенком, хочу поесть", True, ["food"]),
    ("С детьми в музей", True, ["culture"]),
    ("У меня двое детей, куда пойти?", True, ["kids", "park", "culture"]),
    ("Хочу кофе без ребёнка", False, ["coffee", "library", "cowork"]),
    ("Хочу кофе без детей", False, ["coffee", "library", "cowork"]),
    ("Coffee without my kids", False, ["coffee", "library", "cowork"]),
    ("Coffee with my children", True, ["coffee", "library", "cowork"]),
])
def test_child_requirement_does_not_replace_the_requested_activity(query, child, categories):
    req = RecommendRequest.model_validate({**ASK, "query": query})
    intent = rule_intent(req)
    assert (intent.companions == "child") is child
    assert intent.categories == categories
    req.context.companions = "child"
    assert rule_intent(req).companions == "child"  # explicit setting stays stricter


@pytest.mark.parametrize("query,mode", [
    ("Хочу погулять бесплатно", "free_only"), ("Куда пойти без расходов?", "free_only"),
    ("Хочу кофе без обязательных покупок", "no_required_purchase"),
    ("A free walk with children", "free_only"), ("Баламен тегін қайда баруға болады?", "free_only"),
    ("Хочу кофе с бесплатным Wi-Fi", "any"), ("Coffee with free wifi", "any"),
    ("Хочу кофе, не обязательно бесплатно", "any"),
    ("Хочу погулять, бюджет до 2 000 тенге", "free_only"),
])
def test_expense_constraints_and_negations(query, mode):
    assert expense_mode(query) == mode


def test_money_not_mistaken_for_time_and_feedback_never_weakens_expenses():
    assert spending_limit("30 минут, бюджет до 2 000 тенге") == 2000
    assert spending_limit("бюджет 30 минут") is None
    req = RecommendRequest.model_validate({**ASK, "query": "Кофе без расходов",
        "feedback": {"reason": "no_expense"}})
    assert apply_feedback(req).preferences.expense_mode == "free_only"
    assert req.preferences.expense_mode == "any"


@pytest.mark.parametrize("weather", [
    {"temp_c": -20, "wind_ms": 2}, {"temp_c": 10, "wind_ms": 12},
    {"temp_c": 8, "wind_ms": 3, "precip_mm": 4}, {"temp_c": 36, "wind_ms": 2},
])
def test_bad_forecast_selects_indoor_but_respects_explicit_outdoor_choice(weather):
    req = RecommendRequest.model_validate({**ASK, "query": "Куда сходить с ребёнком?",
        "context": {**ASK["context"], "weather": weather}})
    assert indoor_required(req)
    intent = rule_intent(req)
    assert "park" not in intent.categories
    req.query = "С ребёнком, но всё равно хотим на улице"
    assert not indoor_required(req)
    req.preferences.indoor_only = True
    assert indoor_required(req)


@pytest.mark.parametrize("query", [
    "С ребенком, на улице дождь. Куда пойти?", "Идет дождь, хочу погулять",
    "With children, it's raining. Where can we go?", "Баламен, далада жаңбыр жауып тұр",
])
def test_text_rain_is_a_shelter_request_even_when_forecast_is_missing(query):
    req = RecommendRequest.model_validate({**ASK, "query": query})
    assert indoor_required(req)
    assert req.context.weather is None


def synthetic(**changes):
    return POI(poi_id="synthetic", name="SYNTHETIC Cafe", lat=51.128, lon=71.430,
        category="coffee", indoor=True, kid_friendly=True,
        hours_source="osm", opening_hours_raw="Mo-Su 10:00-22:00", **changes)


@pytest.mark.parametrize("hours,arrival,minutes,closed", [
    ("Mo-Su 10:00-15:10", "15:00", 20, True),
    ("Mo-Su 10:00-15:00,15:10-22:00", "14:55", 30, True),
    ("Mo-Su 10:00-15:20", "15:00", 20, False),
    ("Mo-Su 20:00-02:00", "23:50", 40, False),
    ("by appointment", "15:00", 20, False),
])
def test_whole_visit_hours(hours, arrival, minutes, closed):
    poi = synthetic().model_copy(update={"opening_hours_raw": hours})
    start = datetime.fromisoformat(f"2026-10-20T{arrival}:00+05:00")
    assert closed_during_visit(poi, start, start + timedelta(minutes=minutes)) is closed


def test_closing_in_the_last_partial_minute_is_not_missed():
    poi = synthetic().model_copy(update={"opening_hours_raw": "Mo-Su 10:00-15:00"})
    arrival = datetime.fromisoformat("2026-10-20T14:59:50+05:00")
    assert closed_during_visit(poi, arrival, arrival + timedelta(seconds=20))


def test_recommendations_exclude_venues_closing_before_arrival_or_during_visit():
    req = RecommendRequest.model_validate(ASK)
    now = datetime.fromisoformat(ASK["context"]["now"])
    base = synthetic()
    pois = [base.model_copy(update={"poi_id": "closed_before_arrival", "lat": 51.130,
                "opening_hours_raw": "Mo-Su 10:00-15:01"}),
            base.model_copy(update={"poi_id": "closes_during_stay", "opening_hours_raw": "Mo-Su 10:00-15:10"}),
            base.model_copy(update={"poi_id": "fits"})]
    result = Retriever(Dataset(pois, "synthetic", 0, 0), None).search(req, rule_intent(req), now, diversify=False)
    assert [h.poi.poi_id for h in result.hits] == ["fits"]
    assert all(c.excluded_because == "closed_at_visit" for c in result.excluded)


@pytest.mark.parametrize("query,allowed", [
    ("Хочу кофе без расходов", {"team_coffee"}),
    ("Хочу кофе без обязательных покупок", {"team_coffee", "team_second"}),
    ("Хочу кофе до 2000 тенге", {"team_coffee"}),
])
def test_real_pipeline_honors_text_spending_constraints(api, query, allowed):
    result = post(api, "/recommend", {**ASK, "query": query})
    assert result["recommendations"]
    assert {c["poi_id"] for c in result["recommendations"]} == allowed
    if "2000" in query:
        assert any("2000" in n and "цены не подтверждены" in n for n in result["notes"])
    denied = post(api, "/plans/build", {"request": {**ASK, "query": query}, "stop_ids": ["team_paid"]})
    assert denied["status"] == "no_matches" and not denied["stops"]
    assert denied["exclusions"][0]["reason"] in ("free_access_unconfirmed", "no_purchase_unconfirmed")


@pytest.mark.parametrize("weather", [
    {"temp_c": -20, "wind_ms": 3}, {"temp_c": 8, "wind_ms": 3, "precip_mm": 5},
])
def test_2gis_child_weather_filter_is_shared_by_cards_and_nearby_list(settings, weather):
    settings.twogis_enabled, settings.twogis_api_key = True, "synthetic"
    items = [place(1, name="SYNTHETIC outside", rubrics=[{"name": "Детские площадки"}]),
             place(2, name="SYNTHETIC inside", rubrics=[{"name": "Детские игровые залы"}])]
    with TestClient(create_app(settings, twogis_transport=transport(items))) as c:
        request = {**ASK, "source": "2gis", "query": "Я с ребёнком, есть час",
                   "context": {**ASK["context"], "weather": weather}}
        result = post(c, "/recommend", request)
        assert result["applied_preferences"]["indoor_only"]
        assert [p["name"] for p in result["recommendations"]] == ["SYNTHETIC inside"]
        assert [p["name"] for p in result["nearby_places"]] == ["SYNTHETIC inside"]
        assert result["considered"]["radius_m"] <= 500 and result["safety"]


def test_provider_child_facilities_require_positive_evidence():
    req = RecommendRequest.model_validate(ASK)
    for label, expected in [("Детская комната", True), ("Нет детской комнаты", False)]:
        p = to_poi(place(attribute_groups=[{"attributes": [{"name": label}]}]), req, 1500)
        assert p.kid_friendly is expected


@pytest.mark.parametrize("scenario", json.loads(
    (Path(__file__).resolve().parents[1] / "frontend/scenarios.json").read_text(encoding="utf-8")))
@pytest.mark.parametrize("variant", ["normal", "rain", "child", "short", "free"])
def test_six_scenarios_times_five_constraints(service, scenario, variant):
    req = RecommendRequest.model_validate(scenario["request"])
    if variant == "rain":
        req.context.weather = Weather(temp_c=8, wind_ms=3, precip_mm=5)
    elif variant == "child":
        req.context.companions = "child"
    elif variant == "short":
        req.context.time_budget_min = 15
    elif variant == "free":
        req.query += ". Без расходов"
    normalized = apply_feedback(req)
    intent, now, result = service.inspect(req)
    if variant == "rain":
        assert normalized.preferences.indoor_only
    if variant == "free":
        assert normalized.preferences.expense_mode == "free_only"
    for hit in result.hits:
        assert hit.candidate.walk_min + hit.stay + (
            hit.candidate.walk_min if hit.to_end is None else hit.to_end) + result.reserve <= intent.time_budget_min
        if variant == "rain":
            assert hit.poi.indoor and hit.candidate.distance_m <= 500
        if intent.companions == "child":
            assert hit.poi.kid_friendly and not hit.poi.adult_only and hit.poi.category != "night"
        if variant == "free":
            assert service.features.condition(hit.poi.poi_id, now.date()).kind == "free"
