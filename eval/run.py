"""Reproducible fixture evaluation; never invents live-AI or human scores."""

import argparse
import asyncio
import json
import logging
import statistics
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from backend.app import scenarios
from backend.config import ROOT, Settings
from backend.intent import rule_intent
from backend.schemas import RecommendRequest
from backend.service import RecommendationService


async def run(args):
    settings = Settings.from_env()
    settings.warm_cache = False
    if not args.ai:
        settings.gemini_api_key = ""
    if args.ai and not settings.gemini_api_key:
        raise SystemExit("--ai requires GEMINI_API_KEY; no AI report was produced")
    service = RecommendationService(settings)
    source = json.loads(Path(args.scenarios).read_text(encoding="utf-8"))
    cases = source["cases"]
    out = Path(args.output)
    (out / "answers").mkdir(parents=True, exist_ok=True)
    counters = dict(
        queries=len(cases),
        responses_with_cards=0,
        four_parts=0,
        within_budget=0,
        cards=0,
        invented_ids=0,
        unsupported_open_claims=0,
        intent_correct=0,
    )
    elapsed, cached_times, retrieval_times, modes = [], [], [], []
    allowed = {p.poi_id for p in service.dataset.pois}
    for row in cases:
        req = RecommendRequest.model_validate(row["request"])
        intent = rule_intent(req).model_dump()
        counters["intent_correct"] += all(intent[k] == v for k, v in row["expected_intent"].items())
        start = time.perf_counter()
        service.inspect(req)
        retrieval_times.append((time.perf_counter() - start) * 1000)
        start = time.perf_counter()
        result, error = await service.recommend(req, use_cache=False)
        elapsed.append((time.perf_counter() - start) * 1000)
        modes.append(result.mode)
        cards = result.recommendations
        counters["responses_with_cards"] += bool(cards)
        counters["four_parts"] += bool(cards) and all(
            c.why and c.what_to_do and c.time_to_spend_min > 0 and c.distance_m >= 0 and c.walk_min >= 0 for c in cards
        )
        counters["cards"] += len(cards)
        for c in cards:
            counters["within_budget"] += c.budget_breakdown.total_min <= result.considered.time_budget_min
            counters["invented_ids"] += c.poi_id not in allowed
            counters["unsupported_open_claims"] += c.open_status.state == "open" and (
                not c.open_status.hours or c.open_status.source == "none"
            )
        (out / "answers" / f"{row['id']}.json").write_text(result.model_dump_json(indent=2) + "\n", encoding="utf-8")
    for row in scenarios():
        req = RecommendRequest.model_validate(row["request"])
        await service.recommend(req, force_no_ai=not args.ai)
        start = time.perf_counter()
        response, _ = await service.recommend(req, force_no_ai=not args.ai)
        if response.mode == "cached":
            cached_times.append((time.perf_counter() - start) * 1000)
    log_path = out / "privacy_check.log"
    handler = logging.FileHandler(log_path, mode="w", encoding="utf-8")
    handler.setFormatter(logging.Formatter("%(message)s"))
    logger = logging.getLogger("seruen")
    logger.addHandler(handler)
    logger.setLevel(logging.INFO)
    # Exercise the actual API logging path with fixture data, not reconstructed logs.
    from fastapi.testclient import TestClient
    from backend.app import create_app

    with TestClient(create_app(settings)) as client:
        for row in cases:
            client.post("/recommend", json=row["request"])
    handler.close()
    logger.removeHandler(handler)
    log_text = log_path.read_text(encoding="utf-8")
    private_values = [r["request"]["query"] for r in cases] + [
        str(r["request"]["location"][k]) for r in cases for k in ("lat", "lon")
    ]
    privacy_pass = not any(value in log_text for value in private_values)
    ratings = None
    rating_file = out / "human_ratings.json"
    if not rating_file.exists():
        rating_file.write_text(
            json.dumps({r["id"]: [None, None, None] for r in cases}, ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
        )
    else:
        raw = json.loads(rating_file.read_text(encoding="utf-8"))
        values = [v for row in cases for v in raw.get(row["id"], [])]
        if len(values) == 3 * len(cases) and all(type(v) in (int, float) and 1 <= v <= 5 for v in values):
            ratings = statistics.mean(values)
    report = dict(
        **counters,
        data_kind=settings.data_kind,
        provenance=source["provenance"],
        mode="ai_requested" if args.ai else "no_ai",
        actual_modes=sorted(set(modes)),
        mean_response_ms=round(statistics.mean(elapsed), 3),
        max_response_ms=round(max(elapsed), 3),
        mean_cached_ms=round(statistics.mean(cached_times), 3) if cached_times else None,
        cached_scenarios=len(cached_times),
        mean_retrieval_ms=round(statistics.mean(retrieval_times), 3),
        max_retrieval_ms=round(max(retrieval_times), 3),
        privacy_pass=privacy_pass,
        manual_mean=ratings,
        **service.metrics,
    )
    (out / "report.json").write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    n, count = len(cases), counters["cards"]
    lines = [
        "# Eval Серуен",
        "",
        f"Данные: **{settings.data_kind}**. Источник сценариев: {source['provenance']}.",
        "Это проверка программных инвариантов на смоделированных данных, не оценка реальных мест.",
        "",
        "| Метрика | Результат |",
        "|---|---|",
        f"| Ответы с карточками | {counters['responses_with_cards']}/{n} |",
        f"| Все 4 части ответа | {counters['four_parts']}/{n} |",
        f"| Карточки в бюджете, включая обратную дорогу и запас | {counters['within_budget']}/{count} |",
        f"| ID вне базы | {counters['invented_ids']} |",
        f"| Открыто без часов/источника | {counters['unsupported_open_claims']} |",
        f"| Разбор намерения, включая явный контекст | {counters['intent_correct']}/{n} ({counters['intent_correct'] / n:.1%}) |",
        f"| Средний ответ {report['actual_modes']} | {report['mean_response_ms']} мс |",
        f"| Средний кеш / прогрето | {report['mean_cached_ms']} мс / {len(cached_times)}/6 |",
        f"| Поиск средний / максимум | {report['mean_retrieval_ms']} / {report['max_retrieval_ms']} мс |",
        f"| Проверка реальных логов API | {'PASS' if privacy_pass else 'FAIL'} |",
        f"| Ручная оценка 3 × {n} | {ratings if ratings is not None else 'НЕ ПРОВЕДЕНА'} |",
        "",
        "Живой Gemini: "
        + (
            "вызван; смотрите actual_modes и ai_errors в report.json."
            if args.ai
            else "**НЕ ПРОВЕРЕН**, ключ не использовался."
        ),
        "Доступность расписаний на настоящих местах, качество нейросетевых эмбеддингов и человеческая релевантность этим прогоном не измеряются.",
        "Сценарии содержат заданный бюджет/контекст; разбор свободных формулировок времени отдельно проверяется автотестами.",
        "Полные ответы: answers/*.json. Для человеческой оценки заполнить human_ratings.json тремя оценками 1–5 на каждый ответ.",
        "",
    ]
    (out / "report.md").write_text("\n".join(lines), encoding="utf-8")
    print(json.dumps(report, ensure_ascii=False, indent=2))
    if (
        counters["responses_with_cards"] != n
        or counters["four_parts"] != n
        or counters["within_budget"] != count
        or counters["invented_ids"]
        or counters["unsupported_open_claims"]
        or not privacy_pass
    ):
        raise SystemExit(1)


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--ai", action="store_true")
    parser.add_argument("--scenarios", default=str(ROOT / "eval/scenarios.json"))
    parser.add_argument("--output", default=str(ROOT / "eval"))
    asyncio.run(run(parser.parse_args()))
