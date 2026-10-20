"""Real EXPO correction, branch-safe links and honest provider failure recovery."""
import copy
import json

import httpx
import pytest
from fastapi.testclient import TestClient

from backend.app import create_app
from backend.config import ROOT, Settings
from backend.discovery import to_poi
from backend.geo import haversine
from backend.places import PlacesError
from backend.schemas import RecommendRequest
from backend.twogis import TwoGis
from test_discovery import ASK, place

PID = "team_cafe_coffeeboom_expo"
GID = "70000001072135261"
COORDS = {"lat": 51.088679, "lon": 71.41551}


def test_s1_card_links_route_and_old_destination_use_correct_branch():
    settings = Settings(warm_cache=False, photos_enabled=False)
    scenario = json.loads((ROOT / "frontend/scenarios.json").read_text())[0]["request"]
    req = {**copy.deepcopy(scenario), "source": "local", "finish_mode": "place"}
    with TestClient(create_app(settings)) as client:
        response = client.post("/recommend", json=req)
        assert response.status_code == 200
        coffee = next(r for r in response.json()["recommendations"] if r["poi_id"] == PID)
        assert coffee["coords"] == COORDS
        assert coffee["links"]["2gis"] == f"https://2gis.kz/astana/firm/{GID}"
        distance = haversine(req["location"]["lat"], req["location"]["lon"], **{
            "lat2": COORDS["lat"], "lon2": COORDS["lon"]})
        assert abs(coffee["distance_m"] - distance) <= 1
        assert coffee["rating"] is None  # no copied or invented current rating
        assert coffee["offline_allowed"] is False
        # An already-open old UI may send the old coordinate; the exact ID wins.
        plan = client.post("/plans/build", json={"request": req, "stop_ids": [PID],
            "finish_mode": "destination", "finish_poi_id": PID,
            "destination": {"lat": 51.090488, "lon": 71.41574}})
        assert plan.status_code == 200
        built = plan.json()
        assert built["fits"] and built["stops"][0]["coords"] == COORDS
        assert {k: built["state"]["finish"][k] for k in COORDS} == COORDS
        # Other Coffee BOOM branches keep their own coordinates and get no EXPO identity.
        features = client.app.state.service.features
        other = features.pois["osm_node_10170946742"]
        assert (other.lat, other.lon) == (51.1215924, 71.4281745)
        assert features.twogis_id(other.poi_id) is None


def test_local_fallback_exposes_refusal_and_details_preserve_requested_id():
    calls = []
    def respond(request):
        calls.append(request)
        return httpx.Response(403)
    settings = Settings(warm_cache=False, photos_enabled=False, twogis_enabled=True, twogis_api_key="test-key")
    with TestClient(create_app(settings, twogis_transport=httpx.MockTransport(respond))) as client:
        req = json.loads((ROOT / "frontend/scenarios.json").read_text())[0]["request"]
        data = client.post("/recommend", json={**req, "source": "auto"}).json()
        assert data["source"] == "local" and data["recommendations"]
        assert data["source_error"] == "twogis_access_denied"
        assert client.get(f"/places/{PID}/2gis").status_code == 503
        assert client.get("/health").json()["twogis"]["last_status"] == "twogis_access_denied"
        assert len(calls) == 1  # shared pause across search and details
        item = place()
        item.update(id=GID, point=COORDS, name="Coffee BOOM")
        client.app.state.twogis.blocked_until = 0
        client.app.state.twogis.transport = httpx.MockTransport(lambda r: httpx.Response(200,
            json={"meta": {"code": 200}, "result": {"items": [item]}}))
        details = client.get(f"/places/{PID}/2gis").json()
        assert details["poi_id"] == PID and details["twogis_place_id"] == GID
        assert details["rating"] == 4.5  # synthetic provider response only
        assert client.get("/health").json()["twogis"]["last_status"] == "ok"


@pytest.mark.parametrize("code,public,status", [(403, "twogis_access_denied", 503), (429, "twogis_quota_exceeded", 429)])
async def test_provider_pause_expires_and_does_not_use_up_local_quota(monkeypatch, code, public, status):
    clock, calls = [100.0], []
    monkeypatch.setattr("backend.twogis.time.monotonic", lambda: clock[0])
    def respond(request):
        calls.append(request)
        return httpx.Response(code if len(calls) == 1 else 200,
                              json={"meta": {"code": 200}, "result": {"items": []}})
    provider = TwoGis(Settings(twogis_enabled=True, twogis_api_key="test-key"), [],
                      httpx.MockTransport(respond))
    for _ in range(3):
        with pytest.raises(PlacesError) as e:
            await provider.request_items("https://catalog.api.2gis.com/3.0/items", {})
        assert e.value.code == public and e.value.status == status
    assert len(calls) == 1 and provider.day_calls == 1
    clock[0] += 301
    await provider.request_items("https://catalog.api.2gis.com/3.0/items", {})
    assert len(calls) == 2 and provider.last_status == "ok"


@pytest.mark.parametrize("branch_rating", [None, 0])
def test_null_branch_rating_uses_general_rating_in_search_and_details(branch_rating):
    item = place(reviews={"rating": branch_rating, "review_count": 0,
                          "general_rating": 4.8, "general_review_count": 87})
    poi = to_poi(item, RecommendRequest.model_validate(ASK), 1000)
    details = TwoGis.format_details(item, poi.poi_id)
    assert (poi.rating, poi.rating_count) == (4.8, 87)
    assert (details.rating, details.rating_count, details.rating_scope) == (4.8, 87, "unknown")
