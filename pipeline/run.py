"""A8: whole pipeline in one command -> data/poi.json + data/quality_report.md.

    python -m pipeline.run            # reuse raw files in data/raw/ (no network if cached)
    python -m pipeline.run --fresh    # re-collect OSM, re-run enrichment/wiki (needs internet; keys optional)

Without keys: Google enrichment is skipped and descriptions fall back to templates.
"""

import argparse
import json
import subprocess
import sys
from datetime import date, datetime, timezone

from pipeline import __version__
from pipeline.config import POI_PATH, RAW_DIR, latest_raw
from pipeline.dedupe import dedupe, to_poi
from pipeline.describe import describe_all
from pipeline.report import write_report

FULL_PATH = POI_PATH.with_name("poi_full.json")
CONTRACT_FIELDS = (
    "poi_id", "name", "name_kk", "name_en", "lat", "lon", "category", "tags", "description",
    "description_source", "opening_hours_raw", "hours_source", "phone", "website", "rating",
    "rating_count", "popularity", "wheelchair", "kid_friendly", "adult_only", "indoor", "sources", "last_checked",
)


def _step(module: str, *args: str) -> None:
    print(f"\n== {module} ==", flush=True)
    rc = subprocess.call([sys.executable, "-m", module, *args])
    if rc != 0:
        print(f"[run] {module} exited {rc}; continuing with existing raw files", file=sys.stderr)


def _load(prefix: str) -> dict:
    try:
        return json.loads(latest_raw(prefix).read_text(encoding="utf-8"))
    except FileNotFoundError:
        return {}


def _popularity(p: dict) -> float:
    """0-1 from OSM/known features (no ratings stored): marked popularity_source=osm_features."""
    score = (0.2 * bool(p.get("website")) + 0.1 * bool(p.get("phone")) + 0.3 * bool(p.get("wikidata")
             or p["description_source"] == "wikipedia") + 0.2 * bool(p.get("google_place_id"))
             + 0.1 * bool(p.get("opening_hours_raw")) + 0.1 * bool(p.get("name_kk") or p.get("name_en"))
             + 0.1 * min(len(p["tags"]) / 5, 1))
    return round(min(score, 1.0), 2)


def build() -> None:
    osm = _load("osm_")
    if not osm:
        sys.exit("[run] no data/raw/osm_*.json — run with --fresh (needs internet)")
    places = _load("places_")
    wiki = _load("wiki_").get("items", {})

    collected = osm.get("_meta", {}).get("collected_at")
    as_of = date.fromisoformat(collected[:10]) if collected else None  # data age, not build day
    records = [p for e in osm["elements"] if (p := to_poi(e, today=as_of))]
    pois, dropped = dedupe(records)

    matches = places.get("matches", {})
    for p in pois:
        if m := matches.get(p["poi_id"]):
            p["google_place_id"] = m["google_place_id"]
            p["sources"].append("google_places")
        if w := wiki.get(p["poi_id"]):
            p["description"], p["description_source"] = w["description"], "wikipedia"
            p["description_lang"], p["description_url"] = w["lang"], w["source_url"]
            p["descriptions"] = w.get("descriptions", {w["lang"]: w["description"]})
            p["sources"].append("wikipedia")

    generated, gen_stats = describe_all(pois, {p["poi_id"] for p in pois if p.get("description")})
    for p in pois:
        if g := generated.get(p["poi_id"]):
            p.update(g)
            if g["description_method"] == "llm":
                p["sources"].append("gemini")
        p["popularity"] = _popularity(p)
        p["popularity_source"] = "osm_features"
        p.setdefault("rating", None)
        p.setdefault("rating_count", None)

    pois.sort(key=lambda p: p["poi_id"])
    meta = {
        "pipeline_version": __version__,
        "built_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "osm_collected_at": osm.get("_meta", {}).get("collected_at"),
        "places_complete": places.get("_meta", {}).get("complete", True) if places else None,
        "gemini_model": gen_stats["model"],
        "descriptions": {k: gen_stats[k] for k in ("llm", "template", "rejected", "gemini_calls")},
        "count": len(pois),
    }
    # data/poi.json = backend contract (backend/schemas.py POI, extra="forbid"): a plain list, contract fields only.
    # data/poi_full.json = everything (meta, google_place_id, tags_inferred, all wiki languages...).
    contract = [{**{k: p.get(k) for k in CONTRACT_FIELDS}, "hours_source": p.get("hours_source") or "none"}
                for p in pois]
    POI_PATH.write_text(json.dumps(contract, ensure_ascii=False, indent=1), encoding="utf-8")
    FULL_PATH.write_text(json.dumps({"_meta": meta, "pois": pois}, ensure_ascii=False, indent=1), encoding="utf-8")
    (RAW_DIR / "dropped.json").write_text(json.dumps(dropped, ensure_ascii=False, indent=1), encoding="utf-8")
    write_report(pois, dropped, meta)
    print(f"\n[run] {len(pois)} POI -> data/poi.json; dropped {len(dropped)}; report -> data/quality_report.md")
    print(f"[run] descriptions: {meta['descriptions']}")


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--fresh", action="store_true", help="re-collect OSM and re-run enrichment + wiki")
    args = ap.parse_args()
    if args.fresh or not list(RAW_DIR.glob("osm_*.json")):
        _step("pipeline.collect")
    if args.fresh:
        _step("pipeline.enrich")
        _step("pipeline.wiki")
    build()


if __name__ == "__main__":
    main()
