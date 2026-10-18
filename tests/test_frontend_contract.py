import pytest
from backend.app import scenarios


@pytest.mark.parametrize('lang,weekday', [('ru','вс'), ('kk','жс'), ('en','Sun')])
def test_considered_language_and_cache(client, request_data, lang, weekday):
    request_data['context'].update(lang=lang, simulate=True, now='2026-10-18T14:00:00+05:00')
    for _ in range(2):
        data = client.post('/recommend', json=request_data).json()
        assert data['considered']['time'].startswith(weekday)
        assert data['considered']['time_simulated'] is True


def test_route_reserve_and_walk_speed_are_explicit(client):
    request = next(s['request'] for s in scenarios() if s['id'] == 'S5')
    result = client.post('/recommend', json=request).json()
    ctx = result['considered']
    assert ctx['effective_budget_min'] + ctx['reserve_min'] == ctx['time_budget_min']
    assert ctx['reserve_min'] == 60
    assert ctx['walk_speed_m_per_min'] in (60, 75)
    assert ctx['street_factor'] == 1.3
    for card in result['recommendations']:
        assert card['budget_breakdown']['total_min'] <= ctx['time_budget_min']
        assert card['budget_breakdown']['total_min'] - 60 <= ctx['effective_budget_min']
        assert card['description']
        assert card['description_source']
        assert card['sources']


def test_offline_frontend_demos_match_backend():
    import json
    from backend.config import ROOT
    assert json.loads((ROOT / 'frontend/scenarios.json').read_text(encoding='utf-8')) == scenarios()


@pytest.mark.asyncio
async def test_generated_description_is_not_sent_as_verified_fact(service, req, monkeypatch):
    from backend.generate import Gemini
    captured = {}
    intent, _, search = service.inspect(req)
    hit = search.hits[0]
    hit.poi = hit.poi.model_copy(update={'description_source': 'generated', 'description': 'Unverified invented amenity'})
    provider = Gemini(service.settings)

    async def capture(system, payload, schema):
        captured.update(payload)
        return {'recommendations': [{'poi_id': hit.poi.poi_id, 'why': 'A nearby option',
                  'what_to_do': 'Check visitor details', 'time_to_spend_min': 20}]}

    monkeypatch.setattr(provider, 'structured', capture)
    await provider.generate(req, intent, [hit])
    assert captured['candidates'][0]['description'] == ''
    assert captured['candidates'][0]['description_source'] == 'generated'
