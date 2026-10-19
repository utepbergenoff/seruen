"""Synthetic pedestrian routes: preserve the goal and never confirm straight-line breaks."""
import time

import httpx
import pytest
from fastapi.testclient import TestClient

from backend.app import create_app
from backend.routing import WalkingRouter
from backend.schemas import Coords
from test_feature_expansion import ASK, expanded as expanded, plan, post


def routed_response(request, *, fail_via=False, seen=None):
    points = [[float(v) for v in p.split(",")] for p in request.url.path.rsplit("/", 1)[1].split(";")]
    if seen is not None:
        seen.append((time.monotonic(), points))
    moving = sum(a != b for a, b in zip(points, points[1:]))
    if fail_via and moving > 1:
        return httpx.Response(503)
    # Both routes bend around streets. The break adds only 100 m, even though
    # the whole street route is much longer than the 290 m straight estimate.
    distances = [0 if a == b else 500 if moving == 1 else 300 for a, b in zip(points, points[1:])]
    geometry = [points[0]]
    for a, b in zip(points, points[1:]):
        geometry.extend([[(a[0]+b[0])/2+0.0001, (a[1]+b[1])/2], b])
    return httpx.Response(200, json={"code": "Ok", "waypoints": [{"location": p} for p in points],
        "routes": [{"legs": [{"distance": d} for d in distances], "geometry": {"coordinates": geometry}}]})


async def test_rapid_consecutive_routes_keep_street_geometry(settings):
    settings.routing_enabled = True
    seen = []
    router = WalkingRouter(settings, httpx.MockTransport(lambda r: routed_response(r, seen=seen)))
    points = [Coords(lat=51.128, lon=71.430), Coords(lat=51.130, lon=71.430)]
    first = await router.route(points, 75)
    second = await router.route(points, 75)
    assert first.source == second.source == "osrm_foot"
    assert len(seen) == 2 and seen[1][0] - seen[0][0] >= .95
    assert first.geometry == second.geometry and len(second.geometry) > len(points)


def build_goal(client):
    return post(client, "/plans/build", plan(stop_ids=["team_second"], finish_mode="destination",
        destination={"lat":51.130, "lon":71.430}, finish_poi_id="team_second"))


def add_bench(client, previous):
    return client.post("/plans/recalculate", json={"request":ASK, "previous":previous["state"],
        "reason":"add_stop", "poi_id":"team_bench", "remaining_time_min":90, "keep_stops":True})


def test_confirmed_break_has_real_path_through_stop_and_same_goal(expanded):
    expanded.routing_enabled = True
    with TestClient(create_app(expanded, routing_transport=httpx.MockTransport(routed_response))) as client:
        original = build_goal(client)
        response = add_bench(client, original)
        assert response.status_code == 200, response.text
        result = response.json()
        assert result["routing_source"] == "osrm_foot" and result["routing_error"] is None
        assert [p["poi_id"] for p in result["stops"]] == ["team_bench", "team_second"]
        assert result["state"]["finish"] == original["state"]["finish"]
        assert [71.430, 51.129] in result["geometry"]
        assert len(result["geometry"]) > 4 and result["geometry"] != original["geometry"]
        assert result["budget"]["walking_min"] == 8
        assert result["legs"][-1]["walk_min"] == 0


@pytest.mark.parametrize("failure", ["baseline", "via"])
def test_unavailable_router_cannot_confirm_estimated_break(expanded, failure):
    expanded.routing_enabled = True
    failing = False

    def respond(r):
        if failing and failure == "baseline":
            return httpx.Response(503)
        return routed_response(r, fail_via=failing)

    with TestClient(create_app(expanded, routing_transport=httpx.MockTransport(respond))) as client:
        original = build_goal(client)
        failing = True
        response = add_bench(client, original)
        assert response.status_code == 409
        assert response.json()["error"]["code"] == "break_routing_unavailable"
        assert original["state"]["remaining_ids"] == ["team_second"]
