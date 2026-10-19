import asyncio
import copy

import httpx
import pytest
from fastapi.testclient import TestClient

from backend.app import create_app
from backend.discovery import Discovery, to_poi
from backend.schemas import Draft, Generated, RecommendRequest
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
        ids = [x["poi_id"] for x in first["nearby_places"]]
        assert len(ids) == len(set(ids)) == 7 and first["next_cursor"] is None
        assert {x["poi_id"] for x in first["recommendations"]} <= set(ids)
        c.post("/recommend", json=ASK)
        assert len(seen) == 1  # repeated browsing reuses the short-lived page cache
        params = seen[0].url.params
        assert params["q"] == "Кофейни" and params["page_size"] == "10"
        assert "type" not in params and params["sort"] == "distance"
        assert params["point"] == "71.43,51.128"
        assert "synthetic-private-key" not in r.text


def test_catalog_walk_filters_indoor_rubrics_and_supplies_verified_photo_identity(enabled):
    items = [place(1, name="Chaplin", rubrics=[{"name": "Кинотеатры"}]),
             place(2, name="NU Park", rubrics=[{"name": "Парки культуры и отдыха"}]),
             place(3, name="Музей", rubrics=[{"name": "Музеи"}])]
    with TestClient(create_app(enabled, twogis_transport=transport(items))) as c:
        answer = c.post("/recommend", json={**ASK, "query": "Хочу прогуляться"}).json()
        assert [p["name"] for p in answer["recommendations"]] == ["NU Park"]
        assert [p["name"] for p in answer["nearby_places"]] == ["NU Park"]
        discovery = c.app.state.discovery
        pid = answer["recommendations"][0]["poi_id"]
        assert c.app.state.photos.catalog_poi(pid).name == "NU Park"
        recorded, poi = discovery.photo_pois[pid]
        discovery.photo_pois[pid] = (recorded - 301, poi)
        assert discovery.cached_poi(pid) is None


def test_live_eval_accepts_verified_catalog_candidates_but_not_invented_ids(enabled):
    from backend.schemas import RecommendResponse
    from eval.live import grounded_ids

    with TestClient(create_app(enabled, twogis_transport=transport())) as c:
        answer = RecommendResponse.model_validate(c.post("/recommend", json=ASK).json())
        ids = grounded_ids(answer, {"local-only"})
        assert {p.poi_id for p in answer.recommendations} <= ids
        assert "local-only" not in ids and "2gis_invented" not in ids
        answer.nearby_places[0].eligible = False
        assert answer.nearby_places[0].poi_id not in grounded_ids(answer, set())


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


@pytest.mark.parametrize("rubric", ["Детская одежда", "Спортивная одежда / обувь", "Детские игрушки", "Парковки"])
def test_shops_and_parking_are_not_recreation_venues(rubric):
    assert to_poi(place(rubrics=[{"name": rubric}]), RecommendRequest.model_validate(ASK), 1500) is None


def test_child_clubs_are_not_nightclubs():
    poi = to_poi(place(rubrics=[{"name": "Детские / подростковые клубы"}]),
                 RecommendRequest.model_validate(ASK), 1500)
    assert poi.category == "kids" and poi.kid_friendly and not poi.adult_only


def test_park_search_avoids_ambiguous_clothing_query(enabled):
    seen = []
    with TestClient(create_app(enabled, twogis_transport=transport(seen=seen))) as c:
        c.post("/recommend", json={**ASK, "query": "Хочу прогуляться 30 минут"})
    assert seen[0].url.params["q"] == "Парки культуры и отдыха"


def test_duplicate_ids_and_cursor_binding(enabled):
    with TestClient(create_app(enabled, twogis_transport=transport([place(), place(), place(2), place(3), place(4)], total=30))) as c:
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
        assert [r.url.params["page"] for r in seen] == ["1", "2", "3", "4"]
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


class CatalogGemini:
    def __init__(self, broken=False):
        self.calls, self.received, self.broken = 0, [], broken

    async def generate(self, request, intent, hits):
        self.calls += 1
        self.received = hits
        if self.broken:
            raise RuntimeError('private provider diagnostic')
        return Generated(recommendations=[
            Draft(poi_id='invented', why='Не показывать.', time_to_spend_min=10, what_to_do='Не показывать.'),
            Draft(poi_id=hits[-1].poi.poi_id, why='Близкое кафе подходит для короткой остановки.',
                  time_to_spend_min=480, what_to_do='Можно взять кофе и отдохнуть.')])


def test_gemini_selects_catalog_place_with_grounded_final_explanation(enabled):
    enabled.gemini_api_key = 'synthetic-ai-key'
    ai = CatalogGemini()
    with TestClient(create_app(enabled, provider=ai, twogis_transport=transport())) as c:
        d = c.post('/recommend', json=ASK).json()
        assert d['mode'] == 'ai' and len(ai.received) == 7
        assert d['recommendations'][0]['poi_id'] == ai.received[-1].poi.poi_id
        assert '120 мин' in d['recommendations'][0]['why']
        assert d['recommendations'][0]['why_source'] == 'template'
        assert d['recommendations'][0]['selection_source'] == 'ai'
        assert all(p['facts_source']=='2gis' and p['poi_id']!='invented' for p in d['recommendations'])
        assert all(p['budget_breakdown']['total_min'] <= 120 for p in d['recommendations'])
        assert c.app.state.service.metrics['invented_ids_rejected'] == 1
        assert all(h.poi.sources == ['2gis'] for h in ai.received)
        c.post('/recommend', json=ASK)
        assert ai.calls == 1


def test_gemini_failure_keeps_catalog_and_marks_fallback(enabled):
    enabled.gemini_api_key = 'synthetic-ai-key'
    ai = CatalogGemini(True)
    with TestClient(create_app(enabled, provider=ai, twogis_transport=transport())) as c:
        d = c.post('/recommend', json=ASK).json()
        assert d['mode'] == 'no_ai' and len(d['nearby_places']) == 7
        assert d['recommendations'] and d['source_error'] is None
        assert any('ИИ' in note for note in d['notes'])
        assert 'private provider' not in str(d)
        assert c.post('/recommend', json=ASK).json()['mode'] == 'no_ai'
        assert ai.calls == 1  # immediate retries do not consume another free API request
        cache = c.app.state.discovery.ai_cache
        key = next(iter(cache))
        cache[key] = (cache[key][0] - 31, None)
        ai.broken = False
        assert c.post('/recommend', json=ASK).json()['mode'] == 'ai'
        assert ai.calls == 2  # fallback cannot suppress AI recovery indefinitely


def test_coffee_chains_cafe_rubrics_and_closed_places_remain_visible(enabled):
    hours = {day: {'working_hours':[{'from':'01:00','to':'02:00'}]}
             for day in ('Mon','Tue','Wed','Thu','Fri','Sat','Sun')}
    items=[place(1,name='Espresso Day',rubrics=[{'name':'Кафе'}]),
           place(2,name='Coffee Boom',rubrics=[{'name':'Рестораны'},{'name':'Кофейни'},
                                             {'name':'Детские игровые площадки'}]),
           place(3,name='Closed cafe',schedule=hours)]
    with TestClient(create_app(enabled, twogis_transport=transport(items))) as c:
        d=c.post('/recommend',json=ASK).json()
        assert {p['name'] for p in d['recommendations']} == {'Espresso Day','Coffee Boom'}
        assert len(d['nearby_places']) == 3
        closed=next(p for p in d['nearby_places'] if p['name']=='Closed cafe')
        assert not closed['eligible'] and closed['excluded_because']=='closed'


@pytest.mark.parametrize('name',['Coffee Boom','Espresso Day'])
def test_brand_name_is_not_replaced_by_generic_coffee_query(enabled,name):
    seen=[]
    with TestClient(create_app(enabled,twogis_transport=transport(seen=seen))) as c:
        c.post('/recommend',json={**ASK,'query':name})
    assert seen[0].url.params['q']==name


def test_nearby_pagination_covers_all_results_without_duplicates(enabled):
    seen=[]
    def respond(req):
        page=int(req.url.params['page'])
        seen.append(page)
        items=[place(n) for n in range((page-1)*10+1,min(page*10,43)+1)]
        return httpx.Response(200,json={'meta':{'code':200},'result':{'items':items,'total':43}})
    with TestClient(create_app(enabled,twogis_transport=httpx.MockTransport(respond))) as c:
        q=copy.deepcopy(ASK)
        ids=[]
        for _ in range(3):
            d=c.post('/recommend',json=q).json()
            ids += [p['poi_id'] for p in d['nearby_places']]
            if d['next_cursor']:
                q['cursor']=d['next_cursor']
        assert len(ids)==len(set(ids))==43
        assert d['next_cursor'] is None and seen==[1,2,3,4,5]


def test_partial_provider_failure_keeps_first_page_and_retry_cursor(enabled):
    def respond(req):
        if req.url.params['page']=='2':
            return httpx.Response(429)
        return httpx.Response(200,json={'meta':{'code':200},'result':{'items':[place()], 'total':20}})
    with TestClient(create_app(enabled,twogis_transport=httpx.MockTransport(respond))) as c:
        d=c.post('/recommend',json=ASK).json()
        assert d['recommendations'] and d['nearby_places'] and d['next_cursor']
        assert d['source_error']=='twogis_quota_exceeded'


def test_team_place_with_verified_2gis_identity_asks_2gis_by_that_id(enabled):
    seen = []
    with TestClient(create_app(enabled, twogis_transport=transport([place()], seen=seen))) as c:
        features = c.app.state.service.features
        team = next(iter(c.app.state.service.dataset.pois)).poi_id
        features.identities["2gis_70000000000001"] = team   # a verified link, as poi_identity_links gives
        data = c.get(f"/places/{team}/2gis").json()
        assert data["match_method"] == "catalog_id" and data["rating"] == 4.5
        assert seen[0].url.path == "/3.0/items/byid" and "70000000000001" in str(seen[0].url)
        other = list(c.app.state.service.dataset.pois)[1].poi_id
        assert other not in features.identities.values()
        c.get(f"/places/{other}/2gis")   # no link: the old name match path, never the linked id
        assert all("70000000000001" not in str(r.url) for r in seen[1:])
