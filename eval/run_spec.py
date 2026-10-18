"""Evaluate Erlan's 6x5 scenario specification on the real snapshot, without API calls."""

import asyncio
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from backend.config import ROOT, Settings
from backend.schemas import RecommendRequest
from backend.service import RecommendationService


async def run():
    source = json.loads((ROOT / "eval/scenarios_spec.json").read_text(encoding="utf-8"))
    service = RecommendationService(Settings(poi_path=ROOT / "data/poi.json", data_kind="real", warm_cache=False))
    out = ROOT / "eval/real_spec"
    (out / "answers").mkdir(parents=True, exist_ok=True)
    rows = []
    for group in source["scenarios"]:
        for n, query in enumerate(group["queries"], 1):
            context = {k: v for k, v in group["context"].items() if k != "airport_buffer_min"}
            context["simulate"] = True  # evaluate the specified clock time, not the test machine's clock
            request = RecommendRequest(
                location={k: v for k, v in group["location"].items() if k != "preset"},
                context=context,
                query=query["text"],
            )
            result, error = await service.recommend(request, use_cache=False)
            expected, issues = group["expected"], []
            cards = result.recommendations
            if not expected["min_places"] <= len(cards) <= expected["max_places"]:
                issues.append("place_count")
            if expected.get("must_have_safety_note") and not result.safety:
                issues.append("safety_note")
            if result.considered.radius_m > expected.get("max_radius_m", float("inf")):
                issues.append("radius")
            for card in cards:
                if card.category not in expected["categories_allowed"]:
                    issues.append("category:" + card.category)
                if card.category in expected["categories_forbidden"]:
                    issues.append("forbidden_category:" + card.category)
                if card.walk_min > expected["max_walk_min"]:
                    issues.append("walk_limit")
                if card.budget_breakdown.total_min > result.considered.time_budget_min:
                    issues.append("budget")
                # S5 max_total_min means the visit budget after the separately reserved airport time.
                visit = card.budget_breakdown.total_min - card.budget_breakdown.reserve_min
                if visit > expected.get("max_total_min", float("inf")):
                    issues.append("visit_budget")
                if card.open_status.state == "closed":
                    issues.append("closed")
            case_id = f"{group['id']}.{n}"
            (out / "answers" / f"{case_id}.json").write_text(result.model_dump_json(indent=2) + "\n", encoding="utf-8")
            rows.append(
                {
                    "id": case_id,
                    "cards": len(cards),
                    "error": error,
                    "issues": sorted(set(issues)),
                    "category_relaxed": "category_relaxed_with_notice" in result.considered.filters,
                }
            )
    report = {
        "source": "eval/scenarios_spec.json",
        "mode": "no_ai",
        "data_kind": "real",
        "poi_count": len(service.dataset.pois),
        "retrieval_mode": service.retriever.mode,
        "queries": len(rows),
        "passed": sum(not row["issues"] for row in rows),
        "cases": rows,
        "notes": [
            "Fixed scenario times evaluated with simulate=true; preset labels removed from API payload.",
            "S5 max_total_min applies to walk/visit/return before the 60-minute airport reserve.",
            "This checks explicit structural expectations, not human relevance, live AI or facilities on site.",
        ],
    }
    (out / "report.json").write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(report, ensure_ascii=False, indent=2))
    if report["passed"] != report["queries"]:
        raise SystemExit(1)


if __name__ == "__main__":
    asyncio.run(run())
