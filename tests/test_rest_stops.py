"""No credentials: enforce additive, bounded rest stops."""
import copy

import pytest

from test_feature_expansion import ASK, TODAY, api as api, expanded as expanded, plan, post


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


@pytest.mark.parametrize('failure', ['budget', 'closed', 'distant', 'duplicate', 'unverified'])
def test_impossible_extra_stop_does_not_return_a_replacement_route(api, failure):
    original = post(api, '/plans/build', plan(stop_ids=['team_coffee']))
    data = api.app.state.service.features
    target = 'team_bench'
    if failure == 'closed':
        data.pois[target].opening_hours_raw = 'Mo-Su off'
    if failure == 'distant':
        data.pois[target].lat = 51.190
    if failure == 'duplicate':
        target = 'team_coffee'
    if failure == 'unverified':
        data.comfort[target].evidence.verification = 'unverified'
    response = api.post('/plans/recalculate', json={'request': ASK, 'previous': original['state'],
        'reason': 'add_stop', 'poi_id': target, 'remaining_time_min': 5 if failure == 'budget' else 90, 'keep_stops': True})
    assert response.status_code == 409
    assert original['state']['remaining_ids'] == ['team_coffee']


