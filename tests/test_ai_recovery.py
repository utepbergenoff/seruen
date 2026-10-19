import asyncio
import json
import logging

import httpx
import pytest

from backend.generate import AIError, Gemini, validate_drafts
from backend.schemas import Draft, Generated


def reply(data):
    return httpx.Response(200, json={"candidates": [{"finishReason": "STOP",
        "content": {"parts": [{"text": json.dumps(data, ensure_ascii=False)}]}}]})


def generation(hits, **changes):
    draft = {"poi_id": hits[0].poi.poi_id, "why": "Кофейня рядом, дорога занимает немного времени.",
             "what_to_do": "Выпить кофе и открыть ноутбук.", "time_to_spend_min": hits[0].stay,
             "evidence_ids": ["category", "walk"]}
    return {"recommendations": [{**draft, **changes}], "note_to_user": ""}


@pytest.mark.parametrize("invalid", ["language", "schema", "opening_claim"])
async def test_generation_repairs_invalid_text_once(settings, service, req, caplog, invalid):
    settings.gemini_api_key = "private-test-key"
    intent, _, search = service.inspect(req)
    calls = []
    caplog.set_level(logging.INFO, logger="seruen")

    def respond(request):
        payload = json.loads(json.loads(request.content)["contents"][0]["parts"][0]["text"])
        calls.append(payload)
        assert payload["response_language"] == "Russian"
        if len(calls) == 1:
            bad = ({"recommendations": []} if invalid == "schema" else
                   generation(search.hits, why="Nearby coffee stop.", what_to_do="Have coffee.")
                   if invalid == "language" else generation(search.hits, why="Кофейня открыта сейчас."))
            return reply(bad)
        assert "validation_feedback" in payload
        return reply(generation(search.hits))

    result = await Gemini(settings, httpx.MockTransport(respond)).generate(req, intent, search.hits)
    accepted, invented, rejected = validate_drafts(result, search.hits, intent.lang)
    assert len(calls) == 2 and len(accepted) == 1 and invented == rejected == 0
    assert "private-test-key" not in caplog.text and req.query not in caplog.text


async def test_quota_error_is_not_retried(settings, service, req):
    settings.gemini_api_key = "private-test-key"
    intent, _, search = service.inspect(req)
    calls = []

    def respond(request):
        calls.append(request)
        return httpx.Response(429, json={"error": {"message": "private provider text"}})

    with pytest.raises(AIError, match="provider_http_error"):
        await Gemini(settings, httpx.MockTransport(respond)).generate(req, intent, search.hits)
    assert len(calls) == 1


async def test_failed_repair_is_bounded(settings, service, req):
    settings.gemini_api_key = "private-test-key"
    intent, _, search = service.inspect(req)
    calls = []

    def respond(request):
        calls.append(request)
        return reply(generation(search.hits, why="Кофейня открыта сейчас."))

    with pytest.raises(AIError, match="all_drafts_rejected"):
        await Gemini(settings, httpx.MockTransport(respond)).generate(req, intent, search.hits)
    assert len(calls) == 2


def test_laptop_action_is_not_an_opening_hours_claim(service, req):
    intent, _, search = service.inspect(req)
    good = Generated.model_validate(generation(search.hits))
    assert len(validate_drafts(good, search.hits, intent.lang)[0]) == 1
    for claim in ["Кофейня открыта.", "Здесь открыто сейчас.", "Место закрыто."]:
        bad = Generated(recommendations=[Draft(**{**good.recommendations[0].model_dump(), "why": claim})])
        assert not validate_drafts(bad, search.hits, intent.lang)[0]


async def test_repair_respects_callers_shared_deadline(settings, service, req):
    settings.gemini_api_key = "private-test-key"
    intent, _, search = service.inspect(req)
    calls = []

    async def respond(request):
        calls.append(request)
        if len(calls) == 2:
            await asyncio.sleep(1)
        return reply({"recommendations": []})

    with pytest.raises(TimeoutError):
        async with asyncio.timeout(0.05):
            await Gemini(settings, httpx.MockTransport(respond)).generate(req, intent, search.hits)
    assert len(calls) == 2
