import httpx
import pytest
from fastapi.testclient import TestClient

from backend.app import create_app
from backend.generate import AIError
from backend.photos import PhotoRequest, Photos
from backend.places import PlacesError
from backend.schemas import POI

INDEX = "https://seruen-astana.netlify.app/img/places/index.json"
JPEG = b"\xff\xd8\xff" + b"0" * 100


@pytest.fixture
def poi():
    return POI(poi_id="cafe", name="Test Cafe", lat=51.128, lon=71.43, category="coffee")


def transport(places, seen=None):
    def handler(request):
        url = str(request.url)
        if seen is not None:
            seen.append(url)
        if url == INDEX:
            return httpx.Response(200, json={"version": 1, "places": places})
        return httpx.Response(200, content=JPEG, headers={"content-type": "image/jpeg"})
    return httpx.MockTransport(handler)


class FakeAI:
    def __init__(self, answer=None, error=None):
        self.answer, self.error, self.calls = answer, error, []

    async def structured(self, system, payload, schema, images=(), timeout=None):
        self.calls.append({"payload": payload, "images": list(images)})
        if self.error:
            raise self.error
        return self.answer


ANSWER = {"photos": [{"index": 0, "shows_place": True}, {"index": 1, "shows_place": False}],
          "lighting": "natural", "kids_area": "no", "seats": 24, "seating": "some", "space": "medium",
          "decor": "светлое дерево и растения",
          "summary": "Большие окна, около 24 мест и спокойный зал — удобно посидеть с ноутбуком."}
COMMONS = [{"url": "https://upload.wikimedia.org/a.jpg", "page_url": "https://commons.wikimedia.org/wiki/File:A.jpg",
            "author": "A", "license": "CC BY-SA 4.0", "source": "commons"},
           {"url": "https://upload.wikimedia.org/street.jpg", "source": "commons"}]


def make(settings, poi, places, ai, seen=None):
    settings.gemini_api_key = "synthetic-test-key"
    return Photos(settings, [poi], transport(places, seen), ai)


async def test_only_photos_that_show_the_place_are_returned_with_the_analysis(settings, poi):
    ai = FakeAI(ANSWER)
    result = await make(settings, poi, {"cafe": COMMONS}, ai).details("cafe", PhotoRequest(query="поработать"))
    assert result.status == "ok" and result.analysis_source == "gemini"
    assert [p.url for p in result.photos] == ["https://upload.wikimedia.org/a.jpg"]
    assert result.analysis.seats == 24 and result.analysis.lighting == "natural"
    assert "24 мест" in result.analysis.summary
    assert len(ai.calls[0]["images"]) == 2 and ai.calls[0]["payload"]["request"]["query"] == "поработать"


async def test_no_photos_means_no_ai_call(settings, poi):
    ai = FakeAI(ANSWER)
    result = await make(settings, poi, {}, ai).details("cafe", PhotoRequest())
    assert result.status == "no_photos" and not result.photos and not ai.calls


async def test_commons_thumbnail_host_is_loaded_and_analyzed_without_allowing_lookalikes(settings, poi):
    thumb = {**COMMONS[0], "url": "https://thumb.wikimedia.org/wikipedia/commons/thumb/a/ab/Garden.jpg/960px-Garden.jpg"}
    bad_urls = ["https://thumb.wikimedia.org.evil.example/a.jpg", "http://thumb.wikimedia.org/a.jpg",
                "https://thumb.wikimedia.org@evil.example/a.jpg"]
    entries = [thumb] + [{"url": url, "source": "commons"} for url in bad_urls]
    seen, ai = [], FakeAI(ANSWER)
    result = await make(settings, poi, {"cafe": entries}, ai, seen).details("cafe", PhotoRequest())
    assert result.status == "ok" and result.analysis_source == "gemini"
    assert [p.url for p in result.photos] == [thumb["url"]]
    assert seen == [INDEX, thumb["url"]]
    assert len(ai.calls) == 1 and len(ai.calls[0]["images"]) == 1


async def test_street_views_only_are_not_shown(settings, poi):
    answer = {**ANSWER, "photos": [{"index": 0, "shows_place": False}, {"index": 1, "shows_place": False}]}
    result = await make(settings, poi, {"cafe": COMMONS}, FakeAI(answer)).details("cafe", PhotoRequest())
    assert result.status == "not_relevant" and not result.photos and result.analysis is None


async def test_ai_failure_keeps_only_team_photos(settings, poi):
    team = [{"url": "cafe-1.jpg", "source": "team"}]
    photos = make(settings, poi, {"cafe": COMMONS + team}, FakeAI(error=AIError("provider_timeout")))
    result = await photos.details("cafe", PhotoRequest())
    assert result.status == "ai_unavailable" and result.analysis is None
    assert [p.url for p in result.photos] == ["https://seruen-astana.netlify.app/img/places/cafe-1.jpg"]


async def test_unsafe_claims_and_wrong_language_are_dropped(settings, poi):
    answer = {**ANSWER, "summary": "Кафе открыто до 23:00, есть розетки.", "decor": "cozy wooden style"}
    result = await make(settings, poi, {"cafe": COMMONS}, FakeAI(answer)).details("cafe", PhotoRequest(lang="ru"))
    assert result.analysis.summary == "" and result.analysis.decor == ""
    assert result.analysis.kids_area == "no"


async def test_foreign_hosts_are_ignored_and_answers_are_cached(settings, poi):
    seen, ai = [], FakeAI(ANSWER)
    places = {"cafe": COMMONS + [{"url": "https://evil.example/x.jpg", "source": "team"}]}
    photos = make(settings, poi, places, ai, seen)
    await photos.details("cafe", PhotoRequest(query="Кофе"))
    await photos.details("cafe", PhotoRequest(query="  кофе "))
    assert not any("evil.example" in url for url in seen)
    assert len(ai.calls) == 1


async def test_unknown_place(settings, poi):
    with pytest.raises(PlacesError) as exc:
        await make(settings, poi, {}, FakeAI(ANSWER)).details("nope", PhotoRequest())
    assert exc.value.status == 404


def test_photos_endpoint_uses_post_and_rejects_extra_fields(settings):
    with TestClient(create_app(settings, photos_transport=transport({}), photos_ai=FakeAI(ANSWER))) as client:
        poi_id = client.app.state.service.dataset.pois[0].poi_id
        ok = client.post(f"/places/{poi_id}/photos", json={"lang": "ru", "query": "кофе", "companions": "alone"})
        assert ok.status_code == 200 and ok.json()["status"] == "no_photos"
        assert client.post(f"/places/{poi_id}/photos", json={"lang": "ru", "lat": 51.1}).status_code == 422
        assert client.post("/places/unknown/photos", json={}).json()["error"]["code"] == "poi_not_found"
