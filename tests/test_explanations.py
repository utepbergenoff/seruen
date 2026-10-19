"""User-facing claims must follow evidence and the final (not proposed) budget."""
import json

import pytest

from backend.fallback import explanation
from backend.generate import Gemini
from backend.schemas import Budget, Draft, Generated, VisitConditionView
from backend.service import RecommendationService


@pytest.mark.parametrize('lang', ['ru', 'en', 'kk'])
@pytest.mark.parametrize('finish', [False, True])
def test_missing_facilities_are_explicit_and_budget_is_final(service, req, lang, finish):
    intent, _, search = service.inspect(req)
    hit = search.hits[0]
    hit.poi = hit.poi.model_copy(update={'tags': ['wifi', 'sockets'], 'tags_inferred': ['sockets']})
    hit.to_end = 7 if finish else None
    intent.lang, intent.tags = lang, ['wifi', 'sockets', 'quiet']
    budget = Budget(walk_there_min=4, stay_min=20, walk_back_min=0 if finish else 4,
                    walk_to_end_min=7 if finish else None, reserve_min=5, total_min=36 if finish else 33)
    why, todo = explanation(hit, req, intent, budget, VisitConditionView())
    assert f'{budget.total_min}/{intent.time_budget_min}' in why
    assert ('Не подтверждены', 'Unconfirmed', 'Расталмаған')[['ru', 'en', 'kk'].index(lang)] in why
    assert len(why.split()) <= 25 and len(todo.split()) <= 35
    assert ('до финиша', 'to your finish', 'мәреге дейін')[['ru', 'en', 'kk'].index(lang)] in why if finish else True
    assert 'Подходит по категории' not in why


def test_expense_reasons_only_use_matching_evidence(service, req):
    intent, _, search = service.inspect(req)
    hit = search.hits[0]
    budget = Budget(walk_there_min=4, stay_min=20, walk_back_min=4, total_min=28)
    req.preferences.expense_mode = 'free_only'
    unknown, _ = explanation(hit, req, intent, budget, VisitConditionView())
    assert 'бесплатн' not in unknown
    free, _ = explanation(hit, req, intent, budget,
                          VisitConditionView(kind='free', verification='verified'))
    assert 'бесплатный по проверенным данным' in free
    alternative, _ = explanation(hit, req, intent, budget, VisitConditionView(), True)
    assert alternative.startswith('Альтернатива:')


class UnsupportedProse:
    async def intent(self, request, rules):
        return rules

    async def generate(self, request, intent, hits):
        return Generated(recommendations=[Draft(poi_id=hits[0].poi.poi_id, time_to_spend_min=480,
            why='Здесь гарантированы тишина, розетки и бесплатное меню.',
            what_to_do='Возьмите бесплатный ужин.')])


async def test_valid_ai_selection_cannot_invent_facilities_or_prices(settings, req):
    settings.gemini_api_key = 'synthetic-test-key'
    service = RecommendationService(settings, UnsupportedProse())
    response, _ = await service.recommend(req)
    assert response.mode == 'no_ai'
    chosen = response.recommendations[0]
    assert chosen.selection_source == 'rules' and not chosen.ai_reviewed
    assert chosen.why_source == chosen.what_to_do_source == 'template'
    assert 'гарантированы' not in chosen.why and 'бесплатн' not in chosen.what_to_do
    assert chosen.time_to_spend_min < 480
    assert f'{chosen.budget_breakdown.total_min}/{req.context.time_budget_min}' in chosen.why


async def test_gemini_payload_excludes_user_coordinates_and_history(service, settings, req):
    intent, _, search = service.inspect(req)
    req.preferences.visited_poi_ids = ['private-history-id']
    req.preferences.exclude_poi_ids = ['private-excluded-id']
    provider = Gemini(settings)
    provider.feature_data = service.features
    payloads = []

    async def capture(system, payload, schema):
        payloads.append(payload)
        if 'candidates' not in payload:
            return intent.model_dump()
        return Generated(recommendations=[Draft(poi_id=search.hits[0].poi.poi_id,
            why='Место рядом для короткого перерыва.', what_to_do='Осмотрите место.', time_to_spend_min=20,
            evidence_ids=['category'])]).model_dump()

    provider.structured = capture
    await provider.intent(req, intent)
    await provider.generate(req, intent, search.hits)
    for payload in payloads:
        serialized = json.dumps(payload)
        assert all(f'"{key}"' not in serialized for key in ('location', 'end', 'lat', 'lon', 'visited_poi_ids', 'exclude_poi_ids'))
        assert 'private-history-id' not in serialized and 'private-excluded-id' not in serialized
        assert 'category_assumptions' not in serialized
