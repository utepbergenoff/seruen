import asyncio
import copy

import httpx
import pytest
from fastapi.testclient import TestClient

from backend.app import create_app
from backend.discovery import Discovery, to_poi
from backend.schemas import RecommendRequest
from backend.service import RecommendationService
from backend.twogis import TwoGis

ASK = {"location": {"lat": 51.128, "lon": 71.43}, "query": "Хочу кофе",
       "context": {"now": "2026-10-18T14:00:00+05:00", "simulate": True, "time_budget_min": 120, "lang": "ru"}}


def place(n=1, **changes):
    return {"id": str(70000000000000+n), "type": "branch", "name": f"New cafe {n}",
            "point": {"lat": 51.128 + n*0.00001, "lon": 71.43}, "address_name": "Астана, пример 1",
            "rubrics": [{"name": "Кофейни"}], "reviews": {"rating": 4.5, "review_count": 100}, **changes}


def transport(items=None, total=None, seen=None, code=200):
    items = items if items is not None else [place(n) for n in range(1, 8)]

    def respond(req):
        if seen is not None:
            seen.append(req)
        return httpx.Response(code, json={"meta": {"code": code},
            "result": {"items": items, "total": len(items) if total is None else total}})
    return httpx.MockTransport(respond)


@pytest.fixture
def enabled(settings):
    settings.twogis_enabled, settings.twogis_api_key = True, "synthetic-private-key"
    return settings


def test_catalog_places_not_in_local_db_are_returned_and_paginated(enabled):
    seen = []
    with TestClient(create_app(enabled, twogis_transport=transport(seen=seen))) as c:
        assert c.get("/health").json()["twogis"]["search_enabled"]
        assert seen == []
        r = c.post("/recommend", json=ASK, headers={"Origin": "http://localhost:5173"})
        first = r.json()
        assert r.status_code == 200 and r.headers["cache-control"] == "no-store"
        assert r.headers["access-control-allow-origin"] == "http://localhost:5173"
        assert first["source"] == "2gis" and first["data_kind"] == "real"
        assert len(first["recommendations"]) == 3
        assert {x["category"] for x in first["recommendations"]} == {"coffee"}
        assert all(x["facts_source"] == "2gis" and x["sources"] == ["2gis"] for x in first["recommendations"])
        assert all(x["links"]["2gis"].startswith("https://2gis.kz/astana/firm/") for x in first["recommendations"])
        assert all(x["poi_id"] not in c.app.state.twogis.pois for x in first["recommendations"])
        second = c.post("/recommend", json={**ASK, "cursor": first["next_cursor"]}).json()
        third = c.post("/recommend", json={**ASK, "cursor": second["next_cursor"]}).json()
        ids = [x["poi_id"] for d in (first, second, third) for x in d["recommendations"]]
        assert len(ids) == len(set(ids)) == 7 and third["next_cursor"] is None
        assert len(seen) == 1  # paging within the result set does not consume API quota
        params = seen[0].url.params
        assert params["q"] == "Кофейни" and params["page_size"] == "50"
        assert params["point"] == "71.43,51.128"
        assert "synthetic-private-key" not in r.text


@pytest.mark.parametrize("code,expected", [(403, "twogis_access_denied"), (429, "twogis_quota_exceeded"),
                                          (500, "twogis_unavailable")])
def test_provider_failure_never_substitutes_local_pois(enabled, code, expected):
    with TestClient(create_app(enabled, twogis_transport=transport(code=code))) as c:
        data = c.post("/recommend", json=ASK).json()
        assert data["source_error"] == expected and data["source"] == "2gis"
        assert data["recommendations"] == [] and data["next_cursor"] is None


def test_not_found_is_empty_result_and_does_not_fallback(enabled):
    with TestClient(create_app(enabled, twogis_transport=transport(code=404))) as c:
        data = c.post("/recommend", json=ASK).json()
        assert data["recommendations"] == [] and data["source_error"] is None


def test_disabled_explicit_source_and_missing_key(settings, enabled):
    enabled.twogis_api_key = ""
    with TestClient(create_app(enabled, twogis_transport=transport())) as c:
        assert c.post("/recommend", json=ASK).json()["source_error"] == "twogis_not_configured"
    settings.twogis_enabled = False
    with TestClient(create_app(settings, twogis_transport=transport())) as c:
        assert c.post("/recommend", json={**ASK, "source": "2gis"}).json()["source_error"] == "twogis_disabled"


@pytest.mark.parametrize("query", ["напиши код python", "хочу выйти на лед", "construction site"])
def test_refusals_do_not_call_provider(enabled, query):
    seen = []
    with TestClient(create_app(enabled, twogis_transport=transport(seen=seen))) as c:
        assert c.post("/recommend", json={**ASK, "query": query}).json()["recommendations"] == []
    assert not seen


def test_outside_astana_and_no_flight_time_do_not_call(enabled):
    seen = []
    with TestClient(create_app(enabled, twogis_transport=transport(seen=seen))) as c:
        c.post("/recommend", json={**ASK, "location": {"lat": 43.2, "lon": 76.9}})
        c.post("/recommend", json={**ASK, "query": "Перед вылетом", "context": {"time_budget_min": 30}})
    assert not seen


def test_filters_preserve_child_accessibility_budget_and_closed_hours(enabled):
    full_hours = {day: {"working_hours": [{"from": "01:00", "to": "02:00"}]}
                  for day in ("Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun")}
    items = [place(1, schedule=full_hours), place(2, point={"lat": 51.2, "lon": 71.5}),
             place(3, rubrics=[{"name": "Бары"}]), place(4)]
    with TestClient(create_app(enabled, twogis_transport=transport(items))) as c:
        data = c.post("/recommend", json=ASK).json()
        assert [x["poi_id"] for x in data["recommendations"]] == ["2gis_70000000000004"]
        assert data["recommendations"][0]["budget_breakdown"]["total_min"] <= 120
        for override in ({"accessibility": True}, {"companions": "child"}):
            data = c.post("/recommend", json={**ASK, "context": {**ASK["context"], **override}}).json()
            assert data["recommendations"] == []


@pytest.mark.parametrize("bad", [place(id="not-an-id"), place(point={"lat": 0, "lon": 0}),
                                 place(type="building"), place(rubrics=[{"name": "Банки"}]),
                                 place(point={"lat": float("nan"), "lon": 71.43})])
def test_invalid_or_irrelevant_places_are_not_imported(bad):
    assert to_poi(bad, RecommendRequest.model_validate(ASK), 1500) is None


def test_duplicate_ids_and_cursor_binding(enabled):
    with TestClient(create_app(enabled, twogis_transport=transport([place(), place(), place(2), place(3), place(4)]))) as c:
        first = c.post("/recommend", json=ASK).json()
        assert first["next_cursor"]
        for other in ({**ASK, "query": "Хочу поесть"}, {**ASK, "location": {"lat": 51.1, "lon": 71.4}}):
            data = c.post("/recommend", json={**other, "cursor": first["next_cursor"]}).json()
            assert data["source_error"] == "twogis_search_expired"
        assert c.post("/recommend", json={**ASK, "cursor": "made-up"}).json()["source_error"] == "twogis_search_expired"


def test_provider_next_page_and_cursor_expiry(enabled):
    seen = []
    with TestClient(create_app(enabled, twogis_transport=transport([place()], total=51, seen=seen))) as c:
        first = c.post("/recommend", json=ASK).json()
        c.post("/recommend", json={**ASK, "cursor": first["next_cursor"]})
        assert [r.url.params["page"] for r in seen] == ["1", "2"]
        saved = c.app.state.discovery.cursors[first["next_cursor"]]
        c.app.state.discovery.cursors[first["next_cursor"]] = (saved[0]-301, *saved[1:])
        assert c.post("/recommend", json={**ASK, "cursor": first["next_cursor"]}).json()["source_error"] == "twogis_search_expired"


def test_startup_and_explicit_local_never_spend_search_quota(enabled):
    enabled.warm_cache = True
    seen = []
    with TestClient(create_app(enabled, twogis_transport=transport(seen=seen))) as c:
        c.get("/health")
        data = c.post("/recommend", json={**ASK, "source": "local"}).json()
        assert data["source"] == "local"
    assert not seen


def test_dynamic_place_details_use_id_after_restart_and_do_not_need_local_database(enabled):
    seen = []
    with TestClient(create_app(enabled, twogis_transport=transport([place()], seen=seen))) as c:
        data = c.get("/places/2gis_70000000000001/2gis").json()
        assert data["match_method"] == "catalog_id" and data["rating"] == 4.5
        assert seen[0].url.path == "/3.0/items/byid"
        assert c.post("/places/2gis_70000000000001/photos", json={}).json()["status"] == "no_photos"


@pytest.mark.parametrize("lang", ["ru", "kk", "en"])
def test_languages_and_named_business_search(enabled, lang):
    seen = []
    with TestClient(create_app(enabled, twogis_transport=transport(seen=seen))) as c:
        data = c.post("/recommend", json={**ASK, "query": "Starbucks", "context": {**ASK["context"], "lang": lang}}).json()
        assert data["source"] == "2gis" and len(data["recommendations"]) == 3
        assert seen[0].url.params["q"] == "Starbucks"
        assert data["considered"]["lang"] == lang


async def test_simultaneous_searches_share_one_upstream_request(enabled):
    service = RecommendationService(enabled)
    seen = []
    discovery = Discovery(TwoGis(enabled, service.dataset.pois, transport(seen=seen)), service)
    req = RecommendRequest.model_validate(copy.deepcopy(ASK))
    results = await asyncio.gather(*(discovery.recommend(req) for _ in range(3)))
    assert all(len(r[0].recommendations) == 3 for r in results)
    assert len(seen) == 1
