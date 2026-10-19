"""The removed filter must neither reappear nor strand previously saved walks."""
import copy

from backend.schemas import Preferences
from test_feature_expansion import ASK, api as api, expanded as expanded, plan, post

LEGACY = {"atmosphere_example_id": "missing-example", "atmosphere_profile": "green_walk",
          "atmosphere_verified_only": True}


def test_retired_feature_is_absent_from_health_routes_and_schema(api):
    assert not any('atmosphere' in k for k in api.get('/health').json()['features'])
    for path in ('/atmosphere/examples', '/atmosphere/profiles'):
        assert api.get(path).status_code == 404
    assert 'atmosphere' not in str(api.get('/features/status').json())
    assert 'atmosphere' not in str(api.get('/openapi.json').json())
    assert '/places/{poi_id}/photos' in api.get('/openapi.json').json()['paths']


def test_legacy_preferences_are_discarded_without_changing_other_filters():
    parsed = Preferences.model_validate({**LEGACY, 'expense_mode': 'free_only', 'exclude_poi_ids': ['skip']})
    assert not any('atmosphere' in k for k in parsed.model_dump())
    assert parsed.expense_mode == 'free_only' and parsed.exclude_poi_ids == ['skip']


def test_retired_preferences_cannot_filter_or_rerank_current_results(api):
    baseline = post(api, '/recommend', ASK)
    legacy = post(api, '/recommend', {**ASK, 'preferences': LEGACY})
    assert [r['poi_id'] for r in legacy['recommendations']] == [r['poi_id'] for r in baseline['recommendations']]
    assert 'atmosphere' not in str(legacy)


def test_old_saved_walk_refreshes_and_replans_without_the_retired_feature(api):
    req = {**copy.deepcopy(ASK), 'preferences': {**LEGACY, 'expense_mode': 'free_only'}}
    payload = plan(request=req, stop_ids=['team_coffee'])
    built = post(api, '/plans/build', payload)
    assert built['fits'] and [s['poi_id'] for s in built['stops']] == ['team_coffee']
    saved = post(api, '/plans/export', {'plan': payload})
    refreshed = post(api, '/plans/refresh', {'saved': saved, 'request': req})
    assert refreshed['fits'] and 'atmosphere' not in str(refreshed)
    previous = copy.deepcopy(refreshed['state'])
    previous['preferences'].update(LEGACY)
    updated = post(api, '/plans/recalculate', {'previous': previous, 'request': req,
        'reason': 'add_stop', 'poi_id': 'team_bench', 'keep_stops': True, 'remaining_time_min': 90})
    assert [s['poi_id'] for s in updated['stops']] == ['team_bench', 'team_coffee']
    assert updated['state']['finish'] == previous['finish']
    assert updated['applied_preferences']['expense_mode'] == 'free_only'
    assert 'atmosphere' not in str(updated)
