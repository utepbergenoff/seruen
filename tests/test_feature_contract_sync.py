"""Shared contract and real UI-to-FastAPI regression checks; no cloud credentials."""
import copy
import os
import shutil
import socket
import subprocess
import threading
import time

import pytest
import uvicorn

from backend.app import create_app
from backend.config import ROOT
from test_feature_expansion import ASK, plan, post
from test_feature_expansion import api as api, expanded as expanded


def test_health_announces_agreed_contract(api):
    health = api.get('/health').json()
    assert health['feature_contract_version'] == 2
    assert set(health['features']) == {'replan', 'end_point', 'constraints', 'comfort', 'cost', 'atmosphere', 'plan_export'}


def test_request_id_echo_does_not_split_recommendation_cache(api):
    first = post(api, '/recommend', {**ASK, 'request_id': 'one'})
    second = post(api, '/recommend', {**ASK, 'request_id': 'two'})
    assert first['request_id'] == 'one' and second['request_id'] == 'two'
    assert second['mode'] == 'cached'
    assert len(api.app.state.service.cache.entries) == 1
    assert api.post('/recommend', json={**ASK, 'request_id': 'x' * 41}).status_code == 422


def test_finish_is_one_way_and_accepts_a_place_that_round_trip_cannot_fit(api):
    req = copy.deepcopy(ASK)
    req.update(location={'lat': 51.125, 'lon': 71.430}, preferences={'exclude_poi_ids': ['team_coffee']})
    req['context']['time_budget_min'] = 30
    old = post(api, '/recommend', req)
    assert 'team_second' not in [p['poi_id'] for p in old['recommendations']]
    req['end'] = {'lat': 51.130, 'lon': 71.430, 'source': 'preset'}
    new = post(api, '/recommend', req)
    card = next(p for p in new['recommendations'] if p['poi_id'] == 'team_second')
    budget = card['budget_breakdown']
    assert budget['walk_to_end_min'] == 0 and budget['walk_back_min'] == 0
    assert budget['total_min'] == budget['walk_there_min'] + budget['stay_min'] + budget['reserve_min'] <= 30
    assert card['arrival_estimate']
    built = post(api, '/plans/build', {'request': req, 'stop_ids': ['team_second']})
    assert built['state']['finish_mode'] == 'destination' and built['fits']


def test_impossible_finish_and_outside_city_do_not_return_fitting_cards(api):
    req = {**ASK, 'end': {'lat': 51.25, 'lon': 71.65}, 'context': {**ASK['context'], 'time_budget_min': 5}}
    result = post(api, '/recommend', req)
    assert not result['recommendations'] and result['route_impossible']['need_min'] > 5
    req['end'] = {'lat': 40, 'lon': 50}
    assert not post(api, '/recommend', req)['recommendations']


def test_distance_constraint_never_expands_past_user_limit(api):
    result = post(api, '/recommend', {**ASK, 'preferences': {'max_distance_m': 100}})
    assert all(p['distance_m'] <= 100 for p in result['recommendations'])
    assert result['considered']['radius_m'] <= 100
    result = post(api, '/plans/build', plan(request={**ASK, 'preferences': {'max_distance_m': 100}}))
    assert not result['stops']
    assert all(p['reason'] == 'distance_limit' for p in result['exclusions'])


@pytest.mark.parametrize('lang', ['ru', 'en', 'kk'])
def test_cold_is_a_supported_request_in_all_languages(api, lang):
    old = post(api, '/plans/build', plan())
    result = post(api, '/plans/recalculate', {'request': {**ASK, 'context': {**ASK['context'], 'lang': lang}},
        'previous': old['state'], 'reason': 'cold', 'remaining_time_min': 70, 'completed_ids': ['team_coffee']})
    assert result['fits'] and result['status'] == 'ok'
    assert result['stops'] and all(p['poi_id'] != 'team_coffee' for p in result['stops'])
    assert all(leg['walk_min'] <= 5 for leg in result['legs'])


def test_replan_preserves_child_accessibility_reserve_and_text_exclusions(api):
    req = {**ASK, 'query': 'кофе с ребенком, без ТРЦ, до вылета',
           'context': {**ASK['context'], 'time_budget_min': 180, 'accessibility': True}}
    old = post(api, '/plans/build', plan(request=req))
    state = old['state']
    assert state['companions'] == 'child' and state['accessibility'] and state['reserve_min'] == 60
    assert 'shopping' in state['exclude_categories']
    result = post(api, '/plans/recalculate', {'request': {**ASK, 'query': 'warm place'},
        'previous': state, 'reason': 'cold', 'remaining_time_min': 90})
    assert result['status'] != 'refused'
    assert result['state']['companions'] == 'child' and result['state']['accessibility']
    assert result['budget']['reserve_min'] == 60 and 'shopping' in result['state']['exclude_categories']


def test_offline_flag_requires_owned_rights(api):
    result = post(api, '/recommend', ASK)
    assert all(p['offline_allowed'] for p in result['recommendations'] if p['poi_id'].startswith('team_'))
    api.app.state.service.features.owned['team_coffee'].offline_allowed = False
    api.app.state.service.cache.entries.clear()
    result = post(api, '/recommend', {**ASK, 'preferences': {'expense_mode': 'free_only'}})
    assert result['recommendations'] and result['recommendations'][0]['offline_allowed'] is False


def test_actual_frontend_forms_against_fastapi(expanded):
    """Use the real browser scripts and real API over loopback, not matching mocks."""
    assert shutil.which('node') and (ROOT / 'node_modules/jsdom').exists(), 'Run npm ci before this integration test'
    expanded.photos_enabled = False
    sock = socket.socket()
    sock.bind(('127.0.0.1', 0))
    port = sock.getsockname()[1]
    server = uvicorn.Server(uvicorn.Config(create_app(expanded), log_level='error', access_log=False, ws='none'))
    worker = threading.Thread(target=server.run, kwargs={'sockets': [sock]}, daemon=True)
    worker.start()
    try:
        for _ in range(100):
            if server.started:
                break
            time.sleep(.02)
        assert server.started
        result = subprocess.run(['node', '--test', 'tests/frontend/contract.integration.cjs'], cwd=ROOT,
            env={**os.environ, 'SERUEN_TEST_URL': f'http://127.0.0.1:{port}'},
            capture_output=True, text=True, timeout=30)
        assert result.returncode == 0, result.stdout + result.stderr
    finally:
        server.should_exit = True
        worker.join(timeout=3)
        sock.close()
