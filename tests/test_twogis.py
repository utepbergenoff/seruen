import asyncio
import copy
import json
import logging
from datetime import datetime, timezone

import httpx
import pytest
from fastapi.testclient import TestClient

from backend.app import create_app
from backend.config import Settings
from backend.places import PlacesError
from backend.schemas import POI
from backend.twogis import TwoGis


@pytest.fixture
def poi():
    return POI(poi_id="test-coffee", name="Test Coffee", lat=51.128, lon=71.430, category="coffee")


@pytest.fixture
def item(poi):
    return {
        "id": "70000001234567890",
        "name": "Test Coffee, кофейня",
        "type": "branch",
        "name_ex": {"primary": "Test Coffee"},
        "point": {"lat": poi.lat, "lon": poi.lon},
        "address_name": "Тестовый адрес",
        "reviews": {"rating": 4.7, "review_count": 82},
        "schedule": {
            "Mon": {"working_hours": [{"from": "09:00", "to": "23:00"}]},
            "comment": "Тестовое расписание",
            "is_24x7": False,
        },
        "schedule_special": [{"date": "2026-10-18", "working_hours": [{"from": "10:00", "to": "20:00"}]}],
    }


def provider(settings, poi, item, calls=None):
    settings.twogis_api_key, settings.twogis_enabled = "private-demo-key", True

    def respond(request):
        if calls is not None:
            calls.append(request)
        return httpx.Response(200, json={"meta": {"code": 200}, "result": {"items": [item], "total": 1}})

    return TwoGis(settings, [poi], httpx.MockTransport(respond))


def test_twogis_config_key_hidden_and_disabled_by_default(monkeypatch):
    monkeypatch.setenv("TWOGIS_API_KEY", "private-demo-key")
    monkeypatch.delenv("TWOGIS_ENABLED", raising=False)
    s = Settings.from_env()
    assert s.twogis_api_key == "private-demo-key" and not s.twogis_enabled
    assert "private-demo-key" not in repr(s)


async def test_details_match_source_schedule_and_no_rag_mutation(settings, poi, item):
    calls, original = [], poi.model_dump()
    p = provider(settings, poi, item, calls)
    a = await p.details(poi.poi_id)
    b = await p.details(poi.poi_id)
    assert len(calls) == 2  # No persistent provider-content cache or prefetch.
    assert calls[0].url.params["point"] == "71.43,51.128"  # longitude first
    assert calls[0].url.params["radius"] == "150"
    assert a.rating == 4.7 and a.rating_count == 82 and a.rating_scope == "branch"
    assert a.weekly_hours[0].intervals[0].end == "23:00"
    assert a.special_hours[0].date == "2026-10-18"
    assert a.open_now is None and not a.photos_supported
    assert a.match_method == "exact_name_nearby" and a.match_distance_m == 0
    assert a.provider_url == "https://2gis.kz/astana/firm/70000001234567890"
    assert b.checked_at >= a.checked_at and poi.model_dump() == original
    assert "private-demo-key" not in a.model_dump_json()


@pytest.mark.parametrize(
    "language,locale,returned", [("ru", "ru_KZ", "ru"), ("en", "ru_KZ", "ru"), ("kk", "kk_KZ", "kk")]
)
async def test_locale_is_explicit(settings, poi, item, language, locale, returned):
    calls = []
    a = await provider(settings, poi, item, calls).details(poi.poi_id, language)
    assert calls[0].url.params["locale"] == locale and a.language == returned


async def test_verified_id_uses_byid(settings, poi, item):
    poi.twogis_place_id = item["id"]
    poi.name_generic = True
    calls = []
    a = await provider(settings, poi, item, calls).details(poi.poi_id)
    assert calls[0].url.path.endswith("/items/byid") and "q" not in calls[0].url.params
    assert a.match_method == "stored_id"


@pytest.mark.parametrize("mutation", ["wrong_name", "distant", "no_coordinates", "invalid_id", "wrong_stored_id"])
async def test_do_not_return_nearby_or_wrong_branch(settings, poi, item, mutation):
    if mutation == "wrong_name":
        item["name"], item["name_ex"] = "Other Coffee", {}
    elif mutation == "distant":
        item["point"]["lat"] += 0.02
    elif mutation == "no_coordinates":
        item.pop("point")
    elif mutation == "invalid_id":
        item["id"] = "../../secret"
    else:
        poi.twogis_place_id = "70000009999999999"
    with pytest.raises(PlacesError, match="twogis_not_matched"):
        await provider(settings, poi, item).details(poi.poi_id)


@pytest.mark.parametrize("truncated", [False, True])
def test_ambiguous_or_truncated_search_fails_closed(poi, item, truncated):
    second = copy.deepcopy(item)
    second["id"] = "70000001234567891"
    result = {"items": [item] if truncated else [item, second], "total": 20 if truncated else 2}
    with pytest.raises(PlacesError, match="twogis_match_ambiguous"):
        TwoGis.match(poi, result)


@pytest.mark.parametrize(
    "state,code",
    [
        ("disabled", "twogis_disabled"),
        ("mock", "twogis_disabled"),
        ("no_key", "twogis_not_configured"),
        ("unknown", "poi_not_found"),
        ("generic", "twogis_not_matched"),
    ],
)
async def test_no_provider_calls_without_valid_request(settings, poi, item, state, code):
    calls = []
    p = provider(settings, poi, item, calls)
    if state == "disabled":
        settings.twogis_enabled = False
    if state == "mock":
        settings.mock = True
    if state == "no_key":
        settings.twogis_api_key = ""
    if state == "generic":
        poi.name_generic = True
    with pytest.raises(PlacesError, match=code):
        await p.details("unknown" if state == "unknown" else poi.poi_id)
    assert not calls


@pytest.mark.parametrize(
    "status,meta,expected",
    [
        (403, 403, "twogis_access_denied"),
        (200, 403, "twogis_access_denied"),
        (200, 429, "twogis_quota_exceeded"),
        (429, 429, "twogis_quota_exceeded"),
        (500, 500, "twogis_unavailable"),
    ],
)
async def test_http_and_meta_errors_hide_key_and_body(settings, poi, item, caplog, status, meta, expected):
    p = provider(settings, poi, item)
    caplog.set_level(logging.INFO, logger="seruen")
    p.transport = httpx.MockTransport(
        lambda _: httpx.Response(
            status, json={"meta": {"code": meta, "error": "private-demo-key"}, "secret": "provider-secret"}
        )
    )
    with pytest.raises(PlacesError, match=expected):
        await p.details(poi.poi_id)
    messages = [r.message for r in caplog.records if r.name == "seruen"]
    assert p.last_status == expected
    assert not any(s in str(messages) for s in ("private-demo-key", "provider-secret", poi.name))


@pytest.mark.parametrize("invalid", ["bad_json", "null_item", "bad_rating", "bool_rating", "bad_hours", "bad_body"])
async def test_malformed_upstream_response(settings, poi, item, invalid):
    p = provider(settings, poi, item)
    if invalid == "bad_rating":
        item["reviews"]["rating"] = 9
    if invalid == "bool_rating":
        item["reviews"]["rating"] = False
    if invalid == "bad_hours":
        item["schedule"]["Mon"]["working_hours"][0]["from"] = "99:99"
    body = {"meta": {"code": 200}, "result": {"items": [None if invalid == "null_item" else item]}}
    if invalid == "bad_body":
        body = []
    p.transport = httpx.MockTransport(
        lambda _: httpx.Response(200, text="invalid") if invalid == "bad_json" else httpx.Response(200, json=body)
    )
    with pytest.raises(PlacesError, match="twogis_invalid_response"):
        await p.details(poi.poi_id)


async def test_missing_hours_rating_and_org_scope(settings, poi, item):
    item.pop("schedule")
    item.pop("schedule_special")
    item["reviews"] = {"rating": 0, "review_count": 0, "is_org_reviews": True}
    a = await provider(settings, poi, item).details(poi.poi_id)
    assert a.rating is None and a.rating_count == 0 and a.rating_scope == "organization"
    assert a.open_now is None and a.weekly_hours == [] and a.is_24x7 is None


async def test_quota_reservation_is_atomic_and_daily_guard(settings, poi, item):
    settings.twogis_requests_per_minute = 5
    settings.twogis_requests_per_day = 25
    calls = []
    p = provider(settings, poi, item, calls)
    results = await asyncio.gather(*(p.details(poi.poi_id) for _ in range(6)), return_exceptions=True)
    assert len(calls) == 5 and sum(isinstance(x, PlacesError) for x in results) == 1
    p.calls.clear()
    p.day, p.day_calls = datetime.now(timezone.utc).date(), 25
    with pytest.raises(PlacesError, match="twogis_local_limit"):
        await p.details(poi.poi_id)
    assert len(calls) == 5


def test_api_no_startup_calls_and_safe_headers(settings):
    calls = []
    settings.twogis_enabled, settings.twogis_api_key = True, "private-demo-key"

    def respond(req):
        calls.append(req)
        return httpx.Response(200, json={"meta": {"code": 200}, "result": {"items": []}})

    with TestClient(create_app(settings, twogis_transport=httpx.MockTransport(respond))) as c:
        health = c.get("/health").json()["twogis"]
        assert health == {"configured": True, "enabled": True, "last_status": "not_checked",
                          "photos_supported": False, "search_enabled": True}
        assert not calls
        poi = next(p for p in c.app.state.service.dataset.pois if not p.name_generic)
        res = c.get(f"/places/{poi.poi_id}/2gis", headers={"Origin": "http://localhost:5173"})
        assert res.status_code == 404 and len(calls) == 1
        assert res.headers["cache-control"] == "no-store"
        assert res.headers["access-control-allow-origin"] == "http://localhost:5173"
        assert json.loads(res.text)["error"]["code"] == "twogis_not_matched"
        assert c.get("/health").json()["twogis"]["last_status"] == "twogis_not_matched"
        assert c.get("/places/x/2gis?lang=xx").status_code == 422


async def test_timeout_no_exception_url_leak(settings, poi, item):
    p = provider(settings, poi, item)

    def timeout(req):
        raise httpx.ReadTimeout("private-demo-key", request=req)

    p.transport = httpx.MockTransport(timeout)
    with pytest.raises(PlacesError, match="twogis_timeout") as exc:
        await p.details(poi.poi_id)
    assert "private-demo-key" not in str(exc.value)
