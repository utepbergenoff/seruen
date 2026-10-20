import hashlib
import json
from datetime import datetime

import pytest

from backend.config import ROOT
from backend.discovery import to_poi
from backend.embeddings import poi_text
from backend.generate import validate_drafts
from backend.geo import ALMATY
from backend.grounding import evidence, supports_draft
from backend.fallback import action
from backend.intent import rule_intent
from backend.loader import Dataset
from backend.photos import PhotoRequest
from backend.retrieval import Retriever
from backend.schemas import Draft, Generated, POI
from test_photos import ANSWER, COMMONS, JPEG, FakeAI, make, poi as poi


def draft(hit, **changes):
    return Draft(poi_id=hit.poi.poi_id, why="Кофейня рядом для короткого перерыва.",
                 what_to_do="Выпейте кофе и обсудите планы на прогулку.", time_to_spend_min=hit.stay,
                 evidence_ids=["category", "walk"], **changes)


@pytest.mark.parametrize("claim", ["Здесь есть розетки.", "Тихое место для работы.",
    "Бесплатный ужин включён.", "Всего 99 минут на посещение.", "Здесь безопасно.",
    "Сегодня состоится концерт."])
def test_unsupported_claims_rejected_even_with_real_evidence_ids(service, req, claim):
    intent, _, search = service.inspect(req)
    hit = search.hits[0]
    hit.poi = hit.poi.model_copy(update={"tags": [], "tags_inferred": []})
    d = draft(hit).model_copy(update={"why": claim})
    assert not supports_draft(d, hit, req, intent, service.features)


def test_generated_prose_reaches_response_but_not_ranking_or_budget(service, req):
    intent, now, search = service.inspect(req)
    d = draft(search.hits[0])
    response = service.assemble(req, intent, now, search, [d], "ai", "rules", "none", {d.poi_id})
    assert response.mode == "ai"
    assert response.recommendations[0].why.startswith(d.why)
    assert response.recommendations[0].what_to_do == d.what_to_do
    assert response.recommendations[0].why_source == "ai"
    assert response.recommendations[1].why_source == "template"
    bad = d.model_copy(update={"evidence_ids": ["tag:invented-fact"]})
    assert not validate_drafts(Generated(recommendations=[bad]), search.hits, intent.lang,
                               req, intent, service.features)[0]


def test_outdoor_activity_hint_does_not_erase_child_specific_action(service, req):
    intent, _, search = service.inspect(req)
    hit = search.hits[0]
    hit.poi = hit.poi.model_copy(update={"name": "Детская площадка", "category": "kids"})
    assert "ребёнком" in action(hit, intent)


def test_exact_walk_minutes_are_allowed_but_invented_numbers_are_rejected(service, req):
    intent, _, search = service.inspect(req)
    h = search.hits[0]
    d = draft(h).model_copy(update={"why": f"До кофейни {h.candidate.walk_min} минут пешком."})
    assert supports_draft(d, h, req, intent)
    for text in [f"До кофейни {h.candidate.walk_min + 1} минут пешком.", "Здесь 20 розеток."]:
        assert not supports_draft(d.model_copy(update={"why": text}), h, req, intent)


@pytest.mark.parametrize("claim", [
    "Культурный объект находится в двадцати одном шаге ходьбы.",
    "This park is six minutes away, fitting your walk request.",
    "Кофейня в девяти минутах ходьбы.", "Жақын орынға он қадам жүріңіз.",
    "Кафе работает ночью и подходит для перекуса.",
    "Заведение подходит благодаря тегам кофе и крытое помещение.",
    "Пройдитесь по дорожкам и отдохните на скамейке.",
])
def test_live_prose_cannot_disguise_quantities_hours_or_missing_benches(service, req, claim):
    intent, _, search = service.inspect(req)
    h = search.hits[0]
    h.poi = h.poi.model_copy(update={"tags": [], "tags_inferred": []})
    assert not supports_draft(draft(h).model_copy(update={"why": claim}), h, req, intent)


def test_confirmed_bench_and_plain_walk_remain_useful_suggestions(service, req):
    intent, _, search = service.inspect(req)
    h = search.hits[0]
    h.poi = h.poi.model_copy(update={"tags": ["bench"], "tags_inferred": []})
    d = draft(h).model_copy(update={"what_to_do": "Пройдитесь и отдохните на скамейке."})
    assert supports_draft(d, h, req, intent)
    assert supports_draft(d.model_copy(update={"why": "Парк рядом для короткой прогулки."}), h, req, intent)


@pytest.mark.parametrize("name,idea,check", [
    ("Chaplin Cinema", "Идея: дойти туда и посмотреть текущий фильм в зале.",
     "Проверьте расписание и полную длительность сеанса перед покупкой билета."),
    ("City Theatre", "Attend a performance during your visit.",
     "Check the programme and full performance duration before buying a ticket."),
])
def test_generic_visit_budget_does_not_promise_a_full_screening(service, req, name, idea, check):
    intent, _, search = service.inspect(req)
    h = search.hits[0]
    h.poi = h.poi.model_copy(update={"name": name, "category": "culture"})
    d = draft(h).model_copy(update={"what_to_do": idea})
    assert not supports_draft(d, h, req, intent)
    assert supports_draft(d.model_copy(update={"what_to_do": check}), h, req, intent)


@pytest.mark.parametrize("lang,why,todo,claim", [
    ("ru", "Парк рядом для прогулки.", "Погуляйте на открытом воздухе.", "Парк открыт сейчас."),
    ("en", "A nearby park for a walk.", "Enjoy an open-air walk.", "The park is open now."),
    ("kk", "Жақын саябақта серуендеуге болады.", "Ашық ауада серуендеңіз.", "Саябақ қазір ашық."),
])
def test_outdoor_activity_is_not_mistaken_for_an_opening_hours_claim(service, req, lang, why, todo, claim):
    intent, _, search = service.inspect(req)
    d = draft(search.hits[0]).model_copy(update={"why": why, "what_to_do": todo})
    assert validate_drafts(Generated(recommendations=[d]), search.hits, lang)[0]
    d = d.model_copy(update={"what_to_do": claim})
    assert not validate_drafts(Generated(recommendations=[d]), search.hits, lang)[0]


def test_generated_descriptions_and_inferred_amenities_do_not_boost_retrieval(req):
    p = POI(poi_id="a", name="Synthetic A", lat=req.location.lat, lon=req.location.lon,
            category="coffee", tags=["quiet", "sockets"], tags_inferred=["quiet", "sockets"],
            description_source="generated", description="Unverified magical sockets")
    assert "sockets" not in poi_text(p) and "magical" not in poi_text(p)
    proven = p.model_copy(update={"poi_id": "b", "name": "Synthetic B", "lat": p.lat + .0001, "tags_inferred": []})
    intent = rule_intent(req)
    r = Retriever(Dataset([p, proven], "synthetic", 0, 0), None)
    result = r.search(req, intent, datetime(2026, 10, 19, 14, tzinfo=ALMATY), diversify=False)
    assert result.hits[0].poi.poi_id == "b"
    facts = evidence(result.hits[-1], req, intent)
    assert "description" not in facts and "tag:sockets" not in facts


def test_2gis_amenities_require_an_explicit_positive_attribute(req):
    item = {"id": "123", "type": "branch", "name": "Synthetic cafe", "point": {
        "lat": req.location.lat, "lon": req.location.lon}, "rubrics": [{"name": "Кофейни"}],
        "attribute_groups": [{"attributes": [{"name": "Wi-Fi"}, {"name": "Нет розеток"}]}]}
    p = to_poi(item, req, 1000)
    assert p.tags == ["wifi"]
    item.pop("attribute_groups")
    assert to_poi(item, req, 1000).tags == []


async def test_old_frontend_photo_index_cannot_restore_unreviewed_venue_photo(settings, poi, tmp_path):
    settings.photo_review_path = tmp_path / "reviews.json"
    settings.photo_review_path.write_text(json.dumps({"places": {}}))
    ai = FakeAI(ANSWER)
    photos = make(settings, poi, {"cafe": COMMONS}, ai)
    assert (await photos.details("cafe", PhotoRequest())).status == "no_photos"
    assert not ai.calls


async def test_photo_identity_is_bound_to_exact_image_bytes(settings, poi, tmp_path):
    settings.photo_review_path = tmp_path / "reviews.json"
    settings.photo_review_path.write_text(json.dumps({"places": {"cafe": {
        COMMONS[0]["url"]: {"sha256": hashlib.sha256(JPEG + b"different").hexdigest()}}}}))
    ai = FakeAI(ANSWER)
    photos = make(settings, poi, {"cafe": COMMONS[:1]}, ai)
    assert (await photos.details("cafe", PhotoRequest())).status == "no_photos"
    assert not ai.calls


def test_shipped_photo_reviews_have_real_bytes_and_fame_city_has_no_mall_photos():
    reviews = json.loads((ROOT / "data/photo_identity_review.json").read_text(encoding="utf-8"))["places"]
    index = json.loads((ROOT / "frontend/img/places/index.json").read_text(encoding="utf-8"))["places"]
    assert "osm_way_1449322354" not in index and "osm_way_1449322354" not in reviews
    for pid, entries in index.items():
        for entry in entries:
            url = "https://seruen-astana.netlify.app/img/places/" + entry["url"]
            digest = hashlib.sha256((ROOT / "frontend/img/places" / entry["url"]).read_bytes()).hexdigest()
            assert reviews[pid][url]["sha256"] == digest
