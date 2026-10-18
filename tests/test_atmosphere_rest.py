"""No credentials: enforce honest visual evidence and additive, bounded rest stops."""
import copy
from datetime import timedelta

import pytest

from backend.feature_data import AtmosphereRecord
from test_feature_expansion import ASK, TODAY, api, expanded, evidence, plan, post


def profile_request(profile='light_cafe', strict=False, query=''):
    return {**copy.deepcopy(ASK), 'query': query, 'preferences': {
        'atmosphere_profile': profile, 'atmosphere_verified_only': strict}}


def test_profiles_are_everyday_settings_not_landmark_tiles(api):
    profiles = api.get('/atmosphere/profiles').json()['profiles']
    assert len(profiles) == 4
    for p in profiles:
        assert set(p['titles']) == {'ru', 'kk', 'en'}
        assert not {'culture', 'viewpoint', 'unusual'} & set(p['categories'])
    light = profiles[0]
    assert light['reviewed_places'] == 1
    assert light['examples'][0]['poi_id'] == 'team_coffee'


def test_profile_search_keeps_unknown_places_but_never_claims_visual_matches(api):
    result = post(api, '/recommend', profile_request())
    assert len(result['recommendations']) >= 2
    assert result['recommendations'][0]['poi_id'] == 'team_coffee'
    known = next(p for p in result['recommendations'] if p['poi_id'] == 'team_coffee')
    assert known['atmosphere_match']['status'] == 'confirmed'
    assert known['atmosphere_match']['matched_features'] == ['bright', 'visible_seating']
    other = next(p for p in result['recommendations'] if p['poi_id'] != 'team_coffee')
    assert other['atmosphere_match']['status'] == 'unknown'
    assert other['atmosphere_match']['matched_features'] == []
    assert 'По фото' not in other['why']
    assert result['mode'] == 'no_ai'


def test_strict_profile_and_identity_link_use_only_reviewed_photos(api):
    result = post(api, '/recommend', profile_request(strict=True))
    assert [r['poi_id'] for r in result['recommendations']] == ['team_coffee']
    data = api.app.state.service.features
    assert data.match('2gis_7000001', None, TODAY, 'light_cafe').status == 'confirmed'
    assert data.match('2gis_7000002', None, TODAY, 'light_cafe').status == 'unknown'


def test_mood_overrides_generic_walk_category_but_not_safety_or_exclusions(api):
    result = post(api, '/recommend', profile_request(query='Хочу погулять'))
    assert result['recommendations']
    assert all(r['category'] in ['coffee', 'food'] for r in result['recommendations'])
    ask = profile_request(query='на крышу стройки')
    assert not post(api, '/recommend', ask)['recommendations']
    ask = profile_request(); ask['context']['exclude_categories'] = ['coffee', 'food']
    assert not post(api, '/recommend', ask)['recommendations']


def test_generic_indoor_overlap_is_not_photo_similarity(api):
    data = api.app.state.service.features
    row = data.atmosphere['bright-reference'].model_copy(deep=True)
    row.example_id = 'unrelated'; row.poi_id = 'team_second'; row.features = ['indoor', 'traditional']
    data.atmosphere[row.example_id] = row
    assert not data.match('team_second', 'bright-reference', TODAY).matched_features


def test_facade_stale_photo_and_missing_seat_are_not_full_interior_match(api):
    data = api.app.state.service.features
    row = data.atmosphere['bright-reference']
    row.features = ['outdoor', 'bright', 'visible_seating']
    assert data.match('team_coffee', None, TODAY, 'light_cafe').status == 'unknown'
    row.features = ['indoor', 'bright']
    assert data.match('team_coffee', None, TODAY, 'light_cafe').status == 'partial'
    assert not post(api, '/recommend', profile_request(strict=True))['recommendations']
    row.features = ['indoor', 'bright', 'visible_seating']
    row.evidence.checked_at = TODAY - timedelta(days=91)
    assert data.match('team_coffee', None, TODAY, 'light_cafe').status == 'unknown'


def test_unknown_profile_rejected_and_absent_evidence_not_fabricated(api):
    req = profile_request('made-up')
    assert api.post('/recommend', json=req).status_code == 422
    assert not post(api, '/recommend', profile_request('green_inside', True))['recommendations']


def test_comfort_reports_actual_distance_access_and_hours(api):
    rows = post(api, '/comfort/search', {'location': ASK['location'], 'radius_m': 500})
    bench = next(p for p in rows if p['kind'] == 'bench')
    assert 100 < bench['distance_m'] < 130 and bench['walk_min'] == 3
    assert not bench['indoor'] and bench['verified'] and bench['access'] == 'public'
    assert bench['open_status']['state'] == 'open'
    data = api.app.state.service.features
    assert data.condition(bench['poi_id'], TODAY).kind == 'free'
    data.comfort[bench['poi_id']].evidence.verification = 'unverified'
    assert not post(api, '/comfort/search', {'location': ASK['location'], 'radius_m': 500})
    assert data.condition(bench['poi_id'], TODAY).kind == 'unknown'


def test_selected_bench_inserted_before_destination_with_finish_and_cost_preserved(api):
    original = post(api, '/plans/build', plan(stop_ids=['team_coffee']))
    state = copy.deepcopy(original['state'])
    state['preferences']['expense_mode'] = 'free_only'
    result = post(api, '/plans/recalculate', {'request': ASK, 'previous': state, 'reason': 'add_stop',
        'poi_id': 'team_bench', 'remaining_time_min': 90, 'keep_stops': True})
    assert [p['poi_id'] for p in result['stops']] == ['team_bench', 'team_coffee']
    assert result['state']['finish'] == state['finish']
    assert result['stops'][0]['stay_min'] == 5
    assert result['applied_preferences']['expense_mode'] == 'free_only'
    assert result['fits']


def test_plan_and_additive_break_keep_the_destinations_atmosphere_evidence(api):
    req = profile_request(strict=True)
    original = post(api, '/plans/build', plan(request=req, stop_ids=['team_coffee']))
    assert original['stops'][0]['atmosphere_match']['status'] == 'confirmed'
    result = post(api, '/plans/recalculate', {'request': req, 'previous': original['state'],
        'reason': 'add_stop', 'poi_id': 'team_bench', 'remaining_time_min': 90, 'keep_stops': True})
    assert result['fits'] and [r['poi_id'] for r in result['stops']] == ['team_bench', 'team_coffee']
    assert result['stops'][0]['atmosphere_match']['status'] == 'not_requested'
    assert result['stops'][1]['atmosphere_match']['status'] == 'confirmed'
    assert result['stops'][1]['atmosphere_match']['photo_ids'] == original['stops'][0]['atmosphere_match']['photo_ids']


@pytest.mark.parametrize('failure', ['budget', 'closed', 'distant', 'duplicate', 'unverified'])
def test_impossible_extra_stop_does_not_return_a_replacement_route(api, failure):
    original = post(api, '/plans/build', plan(stop_ids=['team_coffee']))
    data = api.app.state.service.features
    target = 'team_bench'
    if failure == 'closed': data.pois[target].opening_hours_raw = 'Mo-Su off'
    if failure == 'distant': data.pois[target].lat = 51.190
    if failure == 'duplicate': target = 'team_coffee'
    if failure == 'unverified': data.comfort[target].evidence.verification = 'unverified'
    response = api.post('/plans/recalculate', json={'request': ASK, 'previous': original['state'],
        'reason': 'add_stop', 'poi_id': target, 'remaining_time_min': 5 if failure == 'budget' else 90, 'keep_stops': True})
    assert response.status_code == 409
    assert original['state']['remaining_ids'] == ['team_coffee']


def test_2gis_profile_uses_branch_identity_without_claiming_unknown_photos(expanded):
    from fastapi.testclient import TestClient
    from backend.app import create_app
    from test_discovery import place, transport
    expanded.twogis_enabled, expanded.twogis_api_key = True, 'synthetic-test-key'
    seen = []
    items = [place(1, id='7000001'), place(2), place(3)]
    with TestClient(create_app(expanded, twogis_transport=transport(items, seen=seen))) as c:
        ask = profile_request(); ask['source'] = '2gis'
        result = post(c, '/recommend', ask)
        assert result['source'] == '2gis'
        assert result['recommendations'][0]['poi_id'] == '2gis_7000001'
        assert result['recommendations'][0]['atmosphere_match']['status'] == 'confirmed'
        assert result['recommendations'][1]['atmosphere_match']['status'] == 'unknown'
        assert all(r['facts_source'] == '2gis' for r in result['recommendations'])
        assert seen[0].url.params['q'] == 'Кофейни'
