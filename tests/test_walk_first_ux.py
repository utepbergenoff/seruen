"""Synthetic regression cases for direction, finishes and provider provenance."""
from copy import deepcopy
from datetime import datetime

import pytest

from backend.discovery import to_poi
from backend.geo import ALMATY
from backend.hours import open_status
from backend.schemas import RecommendRequest
from test_discovery import place
from test_feature_expansion import ASK, api as api, expanded as expanded, plan, post


@pytest.mark.parametrize('latitude,longitude,allowed', [
    (51.129, 71.430, True), (51.1285, 71.4304, True),
    (51.1277, 71.430, False), (51.131, 71.430, False), (51.129, 71.435, False),
])
def test_rest_search_only_returns_forward_corridor(api, latitude, longitude, allowed):
    record = api.app.state.service.features.comfort['team_bench']
    record.poi.lat, record.poi.lon = latitude, longitude
    data = post(api, '/comfort/search', {'location': ASK['location'], 'route_points': [ASK['location'],
        {'lat': 51.130, 'lon': 71.430}], 'on_route_only': True, 'radius_m': 100})
    assert bool(data) == allowed
    if allowed:
        assert data[0]['extra_walk_min'] <= 3


@pytest.mark.parametrize('lat,lon', [(51.1277, 71.430), (51.133, 71.430), (51.129, 71.435)])
def test_manual_break_cannot_bypass_route_direction(api, lat, lon):
    previous = post(api, '/plans/build', plan(stop_ids=['team_second']))
    poi = api.app.state.service.features.pois['team_bench']
    poi.lat, poi.lon = lat, lon
    res = api.post('/plans/recalculate', json={'request': ASK, 'previous': previous['state'],
        'reason': 'add_stop', 'poi_id': 'team_bench', 'remaining_time_min': 90, 'keep_stops': True})
    assert res.status_code == 409
    assert res.json()['error']['code'] == 'break_not_on_route'
    assert previous['state']['remaining_ids'] == ['team_second']


def test_cold_prefers_forward_place_over_closer_place_behind(api):
    places = api.app.state.service.features.pois
    places['behind'] = places['team_coffee'].model_copy(update={'poi_id': 'behind', 'lat': 51.1279})
    original = post(api, '/plans/build', plan(stop_ids=['team_second']))
    result = post(api, '/plans/recalculate', {'request': ASK, 'previous': original['state'],
        'reason': 'cold', 'remaining_time_min': 90, 'keep_stops': True})
    assert [s['poi_id'] for s in result['stops']] == ['team_coffee', 'team_second']
    assert result['state']['finish'] == original['state']['finish']


def test_destination_finish_does_not_add_a_return_leg(api):
    one = post(api, '/plans/build', plan(stop_ids=['team_second'], finish_mode='destination',
        destination={'lat': 51.130, 'lon': 71.430}))
    back = post(api, '/plans/build', plan(stop_ids=['team_second'], finish_mode='return'))
    assert one['legs'][-1]['distance_m'] == 0
    assert back['legs'][-1]['distance_m'] > 0
    assert one['budget']['total_min'] < back['budget']['total_min']


def test_advanced_position_is_replan_start_not_initial_origin(api):
    previous = post(api, '/plans/build', plan(stop_ids=['team_second'], finish_mode='destination',
        destination={'lat': 51.130, 'lon': 71.430}))
    request = deepcopy(ASK); request['location'] = {'lat': 51.1285, 'lon': 71.430}
    result = post(api, '/plans/recalculate', {'request': request, 'previous': previous['state'],
        'reason': 'add_stop', 'poi_id': 'team_bench', 'remaining_time_min': 90, 'keep_stops': True})
    assert result['geometry'][0] == [71.430, 51.129]
    assert result['state']['origin'] == previous['state']['origin']
    assert result['state']['finish'] == previous['state']['finish']


def test_route_search_requires_a_destination_even_without_any_records(api):
    api.app.state.service.features.comfort.clear()
    response=api.post('/comfort/search', json={'location': ASK['location'], 'on_route_only': True})
    assert response.status_code == 422


def test_2gis_partial_hours_and_exceptions_remain_visible_without_false_open_claim():
    item = place(1)
    item['schedule'] = {'Mon': {'working_hours':[{'from':'09:00','to':'18:00'}]}, 'comment':'В праздники уточняйте'}
    item['schedule_special'] = [{'date':'2026-10-19','working_hours':[]}]
    poi=to_poi(item, RecommendRequest.model_validate(ASK), 5000)
    result=open_status(poi, datetime(2026,10,19,12,tzinfo=ALMATY))
    assert result.state == 'closed'
    assert result.today_hours == 'off'
    assert '09:00-18:00' in result.hours
    assert result.schedule_has_exceptions
    assert result.source == '2gis' and result.source_url.startswith('https://2gis.kz/')
    assert result.schedule_note == 'В праздники уточняйте'
    assert 'Tu off' not in result.hours


def test_2gis_attributes_are_facts_not_inferred_free_access(api):
    item=place(1)
    item['attribute_groups']=[{'attributes':[{'name':'Wi-Fi'},{'name':'Средний чек 3500 ₸'}]}]
    poi=to_poi(item, RecommendRequest.model_validate(ASK), 5000)
    condition=api.app.state.service.features.condition(poi.poi_id, datetime.now(ALMATY).date(),poi)
    assert poi.name == item['name']
    assert condition.kind == 'unknown'
    assert condition.provider_attributes == ['Wi-Fi','Средний чек 3500 ₸']
    assert condition.provider_url.startswith('https://2gis.kz/')


def test_malformed_optional_provider_metadata_does_not_drop_a_place():
    item=place(1)
    item.update(attribute_groups={'unexpected':'format'}, schedule_special={'unexpected':'format'})
    poi=to_poi(item, RecommendRequest.model_validate(ASK), 5000)
    assert poi.name == item['name']
    assert poi.provider_attributes == []
    assert poi.published_special_hours == {}
