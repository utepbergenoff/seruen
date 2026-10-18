"""A7: data/quality_report.md — numbers for README and slide 5, generated at the end of the pipeline."""

from collections import Counter

from pipeline import __version__
from pipeline.config import REPORT_PATH
from pipeline.dedupe import CATEGORIES
from pipeline.hours import parse_hours


def _pct(n: int, total: int) -> str:
    return f"{100 * n / total:.0f} %" if total else "—"


def write_report(pois: list[dict], dropped: list[dict], meta: dict) -> str:
    n = len(pois)
    by_cat = Counter(p["category"] for p in pois)
    with_hours = [p for p in pois if p.get("opening_hours_raw")]
    parsed = sum(1 for p in with_hours if parse_hours(p["opening_hours_raw"]) is not None)
    desc = Counter(p["description_source"] for p in pois)
    method = Counter(p.get("description_method") for p in pois if p["description_source"] == "generated")
    wheel = Counter(p["wheelchair"] for p in pois)
    with_access = n - wheel.get("unknown", 0)
    google = sum(1 for p in pois if p.get("google_place_id"))
    reasons = Counter(d["reason"] for d in dropped)

    lines = [
        "# Отчёт о качестве данных",
        "",
        f"Сгенерирован автоматически конвейером v{__version__} · сбор OSM: {meta.get('osm_collected_at', '—')}"
        f" · сборка: {meta.get('built_at', '—')}",
        "",
        "## Главное",
        "",
        "| Показатель | Значение |",
        "|---|---|",
        f"| Всего мест (POI) | **{n}** |",
        f"| Категорий с данными | {sum(1 for c in CATEGORIES if by_cat.get(c))} из {len(CATEGORIES)} |",
        f"| С часами работы | {len(with_hours)} ({_pct(len(with_hours), n)}); разобрано {parsed} из {len(with_hours)}"
        f" ({_pct(parsed, len(with_hours))}) |",
        f"| С описанием | {n} (100 %): Wikipedia {desc.get('wikipedia', 0)}, "
        f"сгенерировано {desc.get('generated', 0)} (ИИ {method.get('llm', 0)}, шаблон {method.get('template', 0)}) |",
        f"| С данными о доступности (wheelchair) | {with_access} ({_pct(with_access, n)}): "
        f"yes {wheel.get('yes', 0)}, limited {wheel.get('limited', 0)}, no {wheel.get('no', 0)} |",
        f"| Сопоставлено с Google Places (place_id) | {google} ({_pct(google, n)})"
        f"{'' if meta.get('places_complete', True) else ' — неполный прогон'} |",
        "| С рейтингом | 0 — рейтинги Google не храним (условия Google); запросы Google Places в бэкенде пока не подключены |",
        f"| Отсеяно | {len(dropped)}: " + ", ".join(f"{k} {v}" for k, v in reasons.most_common()) + " |",
        "",
        "## По категориям",
        "",
        "| Категория | Мест | С часами | Доступность известна |",
        "|---|---|---|---|",
    ]
    for c in CATEGORIES:
        ps = [p for p in pois if p["category"] == c]
        if not ps:
            lines.append(f"| {c} | 0 | — | — |")
            continue
        h = sum(1 for p in ps if p.get("opening_hours_raw"))
        a = sum(1 for p in ps if p["wheelchair"] != "unknown")
        lines.append(f"| {c} | {len(ps)} | {h} ({_pct(h, len(ps))}) | {a} ({_pct(a, len(ps))}) |")
    lines += [
        "",
        "## Источники",
        "",
        "- OpenStreetMap через Overpass API (© участники OpenStreetMap, ODbL).",
        "- Wikipedia / Wikidata — описания достопримечательностей (CC BY-SA), ссылка в поле `description_url`.",
        "- Google Places API (New) — только `place_id` для сопоставления (контент Google не хранится).",
        f"- Gemini ({meta.get('gemini_model') or 'не использовался'}) — короткие описания по тегам, "
        "помечены `description_source = generated`.",
        "",
        "Ограничения: данные OSM могут устареть и неравномерны по районам; у безымянных площадок и скверов "
        "название общее («Детская площадка»); часы работы есть не у всех мест — статус тогда «неизвестно».",
        "",
    ]
    text = "\n".join(lines)
    REPORT_PATH.write_text(text, encoding="utf-8")
    return text
