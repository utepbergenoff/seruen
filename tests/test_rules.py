from datetime import datetime

import pytest

from backend.geo import ALMATY, default_stay, radius_for, target_time
from backend.hours import open_status, schedule_open
from backend.intent import rule_intent
from backend.schemas import Context


@pytest.mark.parametrize(
    ("text", "budget"),
    [
        ("30–60 минут", 60),
        ("1–2 часа", 120),
        ("40 минут", 40),
        ("полчаса", 30),
        ("полчаса-час", 60),
        ("пару часов", 120),
        ("час-два", 120),
        ("2 hours", 120),
        ("2 сағат", 120),
    ],
)
def test_time_from_text(req, text, budget):
    req.query = text
    req.context.time_budget_min = None
    assert rule_intent(req).time_budget_min == budget


@pytest.mark.parametrize(
    ("raw", "time", "expected"),
    [
        ("24/7", "2026-10-18T23:00:00+05:00", True),
        ("Mo-Su 08:00-22:00", "2026-10-18T22:00:00+05:00", False),
        ("Mo-Fr 09:00-18:00", "2026-10-19T12:00:00+05:00", True),
        ("Sa,Su 10:00-20:00", "2026-10-18T14:00:00+05:00", True),
        ("Mo-Su 09:00-12:00,13:00-22:00", "2026-10-18T12:30:00+05:00", False),
        ("Fr-Sa 20:00-02:00", "2026-10-18T01:30:00+05:00", True),
        ("Mo-Su 00:00-24:00", "2026-10-18T23:59:00+05:00", True),
        ("09:00-18:00", "2026-10-18T12:00:00+05:00", True),
        ("ежедневно 09:00-18:00", "2026-10-18T12:00:00+05:00", True),
        ("Mo-Su 09:00-22:00; Su off", "2026-10-18T12:00:00+05:00", False),
        ("Su-Mo 08:00-22:00", "2026-10-19T12:00:00+05:00", True),
        ("Mo-Su off", "2026-10-18T12:00:00+05:00", False),
        ("12:00 - 06:00", "2026-10-18T01:00:00+05:00", True),
        ("Mo-Fr 08:00-00:00, Sa-Su 09:00-00:00", "2026-10-18T12:00:00+05:00", True),
        ("Mo-Su,PH 10:00-22:00", "2026-10-18T23:00:00+05:00", False),
        ("PH,Mo-Su 10:00-22:00", "2026-10-18T12:00:00+05:00", True),
        ("Su, Tu-Fr 11:00-19:00", "2026-10-18T12:00:00+05:00", True),
    ],
)
def test_hours_parser_10_formats(raw, time, expected):
    assert schedule_open(raw, datetime.fromisoformat(time)) is expected


@pytest.mark.parametrize(
    "raw",
    [
        None,
        "by appointment",
        "sunrise-sunset",
        "Mo-Fr 09:00-18:00; PH off",
        "25:30-26:00",
        "Mo-Fr 07:14-23:00; Sa,Su,PH 08:14-23:00",
        "Mo-Sa 07:14-24:00, Su,PH 08:14-01:00",
    ],
)
def test_fr7_no_open_claim_when_unknown(service, raw):
    poi = service.dataset.pois[0].model_copy(update={"opening_hours_raw": raw})
    status = open_status(poi, datetime(2026, 10, 18, 12, tzinfo=ALMATY))
    assert status.state == "unknown" and status.confidence == "low"


def test_hours_stale_and_missing_source(service):
    poi = service.dataset.pois[0]
    assert open_status(poi, datetime(2026, 12, 18, 12, tzinfo=ALMATY)).state == "likely_open"
    assert (
        open_status(poi.model_copy(update={"hours_source": "none"}), datetime(2026, 10, 18, 12, tzinfo=ALMATY)).state
        == "unknown"
    )


def test_now_without_simulation_is_ignored(req):
    req.context.simulate = False
    now = datetime(2026, 10, 17, 10, tzinfo=ALMATY)
    assert target_time(req, rule_intent(req), now) == now


def test_tomorrow_closed_evaluated_on_target_day(service, req):
    req.context.now = datetime(2026, 10, 18, 14, tzinfo=ALMATY)
    req.query = "Музей завтра"
    intent, now, search = service.inspect(req)
    assert now.day == 19 and now.hour == 18
    assert all(h.status.state != "closed" for h in search.hits)


@pytest.mark.parametrize(
    "query", ["сколько стоит такси", "напиши код python", "рецепт лекарства", "какая столица Франции"]
)
async def test_fr9_unrelated_refuses(service, req, query):
    req.query = query
    response, _ = await service.recommend(req, use_cache=False)
    assert not response.recommendations


async def test_fr9_out_of_city_refuses(service, req):
    req.location.lat, req.location.lon = 52, 72
    response, _ = await service.recommend(req)
    assert not response.recommendations and "Астане" in response.notes[0]


async def test_dangerous_activity_refuses(service, req):
    req.query = "Хочу выйти на лед"
    response, _ = await service.recommend(req)
    assert not response.recommendations


async def test_child_excludes_adult_only(service, req):
    req.location.lat, req.location.lon = 51.133, 71.404
    req.query = "С ребёнком есть час"
    response, _ = await service.recommend(req)
    assert response.recommendations
    assert "sample_016" not in [r.poi_id for r in response.recommendations]


async def test_night_radius_and_safety(service, req):
    req.location.lat, req.location.lon = 51.128, 71.430
    req.query = "Ночная прогулка"
    response, _ = await service.recommend(req)
    assert response.considered.radius_m <= 1000
    assert response.safety
    assert all(r.open_status.state != "closed" for r in response.recommendations)


async def test_accessibility_unknown_excluded(service, req):
    req.location.lat, req.location.lon = 51.133, 71.404
    req.context.accessibility = True
    req.query = "Необычное"
    response, _ = await service.recommend(req)
    assert all(r.accessibility == "yes" for r in response.recommendations)
    assert "sample_018" not in [r.poi_id for r in response.recommendations]


def test_formula_from_plan():
    assert int(radius_for(60, 75)) == 865
    assert default_stay(30) == 15 and default_stay(120) == 60


async def test_flight_reserve_and_small_budget(service, req):
    req.query = "2 часа перед вылетом"
    response, _ = await service.recommend(req)
    assert all(r.budget_breakdown.reserve_min == 60 for r in response.recommendations)
    req.context.time_budget_min = 30
    response, _ = await service.recommend(req)
    assert not response.recommendations


async def test_mall_alias(service, req):
    req.context = Context(exclude_categories=["mall"], now=req.context.now, simulate=True)
    assert req.context.exclude_categories == ["shopping"]
    req.query = "Надоели ТРЦ, хочу необычное"
    response, _ = await service.recommend(req)
    assert "exclude:shopping" in response.considered.filters


async def test_empty_query_supported(service, req):
    req.query = ""
    response, _ = await service.recommend(req)
    assert response.recommendations
