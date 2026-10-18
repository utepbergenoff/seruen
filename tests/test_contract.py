import json
import logging

import pytest

from backend.app import create_app, scenarios
from backend.schemas import RecommendResponse


def test_b1_health(client):
    health = client.get("/health")
    assert health.status_code == 200
    assert health.json()["poi_count"] == 24
    assert health.json()["mode_available"] == ["no_ai"]
    assert health.json()["data_kind"] == "sample"


@pytest.mark.parametrize("scenario", scenarios(), ids=lambda s: s["id"])
def test_no_ai_mode_all_scenarios(client, scenario):
    response = client.post("/recommend", json=scenario["request"])
    assert response.status_code == 200
    body = RecommendResponse.model_validate(response.json())
    assert body.mode == "no_ai"
    assert 1 <= len(body.recommendations) <= 3
    assert body.data_kind == "sample"
    for r in body.recommendations:
        assert r.why and r.what_to_do and r.time_to_spend_min and r.distance_m >= 0 and r.walk_min >= 0
        assert r.budget_breakdown.total_min <= scenario["request"]["context"]["time_budget_min"]
        assert r.why_source == r.what_to_do_source == "template"
        assert r.facts_source == "poi_db"
        assert len(r.why.split()) <= 25 and len(r.what_to_do.split()) <= 35
        assert r.links == {}
    assert body.budget_breakdown == body.recommendations[0].budget_breakdown
    assert body.considered.candidates_found >= len(body.recommendations)


def test_b1_mock(settings, request_data):
    from fastapi.testclient import TestClient

    settings.mock = True
    with TestClient(create_app(settings)) as client:
        response = client.post("/recommend", json=request_data).json()
        assert response["mock"] is True
        assert response["mode"] == "no_ai"


@pytest.mark.parametrize(
    "change",
    [
        {"location": {"lat": 91, "lon": 71}},
        {"query": "a" * 1001},
        {"context": {"time_budget_min": -1}},
        {"context": {"now": "2026-10-18T12:00:00"}},
        {"context": {"weather": {"temp_c": 10, "wind_ms": -1}}},
        {"context": {"mode": "drive"}},
    ],
)
def test_invalid_payload(client, request_data, change):
    response = client.post("/recommend", json={**request_data, **change})
    assert response.status_code == 422
    assert "input" not in response.text


def test_fr10_no_coords_in_logs(client, request_data, caplog):
    caplog.set_level(logging.INFO, logger="seruen")
    request_data["query"] = "secret_test_query кофе"
    request_data["location"]["lat"] = 51.0891234
    client.post("/recommend", json=request_data)
    client.get("/candidates", params={"lat": 51.0891234, "lon": 71.4171234, "query": "secret_test_query"})
    client.post("/recommend", json={**request_data, "query": "private_invalid_" * 1000})
    messages = [r.message for r in caplog.records if r.name == "seruen"]
    assert messages
    for text in messages:
        assert (
            "51.089" not in text
            and "71.417" not in text
            and "secret_test_query" not in text
            and "private_invalid" not in text
        )
        assert set(json.loads(text)) == {"mode", "duration_ms", "candidates", "error_code"}


def test_cors(client):
    headers = {
        "Origin": "http://localhost:5173",
        "Access-Control-Request-Method": "POST",
        "Access-Control-Request-Headers": "content-type",
    }
    response = client.options("/recommend", headers=headers)
    assert response.headers["access-control-allow-origin"] == "http://localhost:5173"
    headers["Origin"] = "https://untrusted.invalid"
    assert "access-control-allow-origin" not in client.options("/recommend", headers=headers).headers


def test_candidates_get_and_post_same(client, request_data):
    posted = client.post("/candidates", json=request_data).json()
    got = client.get(
        "/candidates",
        params={
            "lat": 51.089,
            "lon": 71.417,
            "query": request_data["query"],
            "time_budget_min": 120,
            "now": request_data["context"]["now"],
            "simulate": "true",
        },
    ).json()
    assert posted == got
    assert all(c["excluded_because"] is None for c in got["candidates"])


def test_all_endpoints_in_openapi(client):
    paths = client.get("/openapi.json").json()["paths"]
    assert {"/health", "/recommend", "/candidates", "/scenarios"} <= set(paths)
    assert len(client.get("/scenarios").json()) == 6
