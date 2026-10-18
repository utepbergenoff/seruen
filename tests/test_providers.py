import json
import logging
from urllib.parse import parse_qs, urlsplit

import httpx
import pytest
from fastapi.testclient import TestClient

from backend.app import create_app
from backend.config import Settings
from backend.generate import AIError, Gemini
from backend.places import DETAIL_FIELDS, Places, PlacesError, maps_url
from backend.provider_status import http_error_code


@pytest.mark.parametrize("status,reason,expected", [
    (403, "SERVICE_DISABLED", "http_403_service_disabled"),
    (400, "API_KEY_INVALID", "http_400_api_key_invalid"),
    (429, "private_key_or_query", "http_429"),
    (404, None, "http_404"),
])
async def test_gemini_diagnostics_are_bounded(settings, caplog, status, reason, expected):
    settings.gemini_api_key = "secret-test-key"
    caplog.set_level(logging.INFO, logger="seruen")
    response = httpx.Response(status, json={"error": {"message": "secret-provider-body",
                                                    "details": [{"reason": reason}]}})
    with pytest.raises(AIError):
        await Gemini(settings, httpx.MockTransport(lambda _: response)).structured("private-query", {}, {})
    messages = [r.message for r in caplog.records if r.name == "seruen"]
    assert json.loads(messages[0])["error_code"] == expected
    assert not any(s in str(messages) for s in ("secret-test-key", "secret-provider-body", "private-query"))


@pytest.mark.parametrize("body", [None, [], "secret", {"error": None}, {"error": {"details": [None]}}])
def test_invalid_error_body_never_leaks(body):
    assert http_error_code(httpx.Response(400, json=body)) == "http_400"


def test_places_settings_keys_hidden(monkeypatch):
    monkeypatch.setenv("GOOGLE_PLACES_API_KEY", "private-places")
    monkeypatch.setenv("GEMINI_API_KEY", "private-ai")
    monkeypatch.delenv("GOOGLE_PLACES_ENABLED", raising=False)
    settings = Settings.from_env()
    assert settings.google_places_api_key == "private-places"
    assert not settings.google_places_enabled
    assert "private" not in repr(settings)


def mapped_poi(service):
    return service.dataset.pois[0].model_copy(update={"google_place_id": "ChIJ_test-place-id"})


async def test_ids_probe_does_not_request_paid_fields(settings, service):
    settings.google_places_api_key = "private-places"
    requests = []

    def respond(req):
        requests.append(req)
        assert req.headers["X-Goog-FieldMask"] == "id"
        assert req.headers["X-Goog-Api-Key"] == "private-places"
        assert "private-places" not in str(req.url)
        return httpx.Response(200, json={"id": "ChIJ_test-place-id"})

    places = Places(settings, [mapped_poi(service)], httpx.MockTransport(respond))
    await places.probe()
    assert places.probe_status == "ok" and len(requests) == 1
    with pytest.raises(PlacesError, match="places_disabled"):
        await places.details(mapped_poi(service).poi_id)
    assert len(requests) == 1


async def test_live_details_separate_from_osm_and_not_cached(settings, service):
    settings.google_places_enabled, settings.google_places_api_key = True, "private-places"
    poi = mapped_poi(service)
    before = poi.model_dump()
    requests = []

    def respond(req):
        requests.append(req)
        assert req.headers["X-Goog-FieldMask"] == DETAIL_FIELDS
        assert "reviews" not in DETAIL_FIELDS and "photos" not in DETAIL_FIELDS
        return httpx.Response(200, json={"id": poi.google_place_id, "rating": 4.7, "userRatingCount": 82,
            "currentOpeningHours": {"openNow": len(requests) == 1, "weekdayDescriptions": ["Sunday: 9–18"]},
            "regularOpeningHours": {"weekdayDescriptions": ["Sunday: 9–20"]},
            "businessStatus": "OPERATIONAL", "attributions": [{"provider": "Example", "providerUri": "https://example.com"}]})

    places = Places(settings, [poi], httpx.MockTransport(respond))
    first, second = await places.details(poi.poi_id), await places.details(poi.poi_id)
    assert first.rating == 4.7 and first.rating_count == 82
    assert first.open_now is True and second.open_now is False
    assert first.current_weekday_hours != first.regular_weekday_hours
    assert first.attributions[0].provider == "Example"
    assert len(requests) == 2 and poi.model_dump() == before
    assert "private-places" not in first.model_dump_json()


async def test_places_guards_unknown_ids_and_rate(settings, service):
    settings.google_places_enabled, settings.google_places_api_key = True, "private-places"
    poi = mapped_poi(service)
    calls = []

    def respond(req):
        calls.append(req)
        return httpx.Response(200, json={"id": poi.google_place_id})

    places = Places(settings, [poi], httpx.MockTransport(respond))
    with pytest.raises(PlacesError, match="poi_not_found"):
        await places.details("arbitrary-google-id")
    assert not calls
    for _ in range(5):
        result = await places.details(poi.poi_id)
        assert result.rating is None and result.open_now is None
    with pytest.raises(PlacesError, match="places_local_limit"):
        await places.details(poi.poi_id)
    assert len(calls) == 5


@pytest.mark.parametrize("response", [
    httpx.Response(403, text="sensitive_key_value"),
    httpx.Response(200, json={"id": "wrong_place"}),
    httpx.Response(200, text="invalid JSON"),
    httpx.Response(200, json={"id": "ChIJ_test-place-id", "rating": 9}),
])
async def test_places_failure_closed(settings, service, response):
    settings.google_places_enabled, settings.google_places_api_key = True, "private-places"
    places = Places(settings, [mapped_poi(service)], httpx.MockTransport(lambda _: response))
    with pytest.raises(PlacesError) as err:
        await places.details(mapped_poi(service).poi_id)
    assert "sensitive_key_value" not in str(err.value)


def test_places_disabled_api_and_cors(settings):
    with TestClient(create_app(settings)) as client:
        response = client.get("/places/example/details")
        assert response.status_code == 503 and response.json()["error"]["code"] == "places_disabled"
        assert response.headers["cache-control"] == "no-store"
        assert client.get("/health").json()["google_places"] == {
            "configured": False, "details_enabled": False, "ids_probe": "not_configured"}
        preflight = client.options("/places/example/details", headers={"Origin": "http://localhost:5173",
                                    "Access-Control-Request-Method": "GET"})
        assert preflight.headers["access-control-allow-origin"] == "http://localhost:5173"


def test_maps_url_uses_matched_id_and_safe_fallback(service):
    poi = mapped_poi(service)
    assert parse_qs(urlsplit(maps_url(poi)).query)["query_place_id"] == [poi.google_place_id]
    poi.google_place_id = "../../bad?key=secret"
    assert "query_place_id" not in parse_qs(urlsplit(maps_url(poi)).query)
