"""A3: match OSM POI to Google Places (New) -> data/raw/places_YYYYMMDD.json.

Only google place_id + match quality are stored (Google ToS: no long-term storage
of Places content). Ratings/hours are fetched live by the backend when a key exists.
"""

import argparse
import hashlib
import json
import math
import os
import re
import sys
import time
from datetime import datetime, timezone

import requests
from dotenv import load_dotenv
from rapidfuzz import fuzz

from pipeline.config import CACHE_DIR, RAW_DIR, latest_raw

NEARBY_URL = "https://places.googleapis.com/v1/places:searchNearby"
# Pro-SKU fields only (5,000 free calls/month); no rating/hours = no Enterprise SKU.
FIELD_MASK = "places.id,places.displayName,places.location,places.types"
MAX_CALLS = 300

TYPE_GROUPS = {
    "food_drink": ["cafe", "coffee_shop", "restaurant", "bar", "pub", "night_club", "ice_cream_shop"],
    "culture_shop": ["museum", "art_gallery", "performing_arts_theater", "movie_theater", "library", "shopping_mall"],
}
OSM_POPULAR = {
    "amenity": {"cafe", "restaurant", "bar", "pub", "nightclub", "library", "coworking_space",
                "theatre", "cinema", "food_court", "ice_cream", "arts_centre"},
    "tourism": {"museum", "gallery"},
    "shop": {"mall"},
}

MAX_DISTANCE_M = 50
MIN_NAME_SCORE = 85

_GENERIC = re.compile(
    r"\b(кафе|кофейня|ресторан|бар|паб|кофе|coffee|cafe|caf[eé]|restaurant|bar|pub|тц|трц|мега|mall)\b",
    re.I,
)
_PUNCT = re.compile(r"[«»\"'“”„&.,!?()\-–—/]+")


def haversine_m(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    r = 6_371_000
    p1, p2 = math.radians(lat1), math.radians(lat2)
    dp, dl = p2 - p1, math.radians(lon2 - lon1)
    a = math.sin(dp / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dl / 2) ** 2
    return 2 * r * math.asin(math.sqrt(a))


_TRANSLIT = str.maketrans({
    "а": "a", "б": "b", "в": "v", "г": "g", "д": "d", "е": "e", "ё": "e", "ж": "zh", "з": "z",
    "и": "i", "й": "y", "к": "k", "л": "l", "м": "m", "н": "n", "о": "o", "п": "p", "р": "r",
    "с": "s", "т": "t", "у": "u", "ф": "f", "х": "h", "ц": "ts", "ч": "ch", "ш": "sh", "щ": "sch",
    "ъ": "", "ы": "y", "ь": "", "э": "e", "ю": "yu", "я": "ya",
    "ә": "a", "ғ": "g", "қ": "k", "ң": "n", "ө": "o", "ұ": "u", "ү": "u", "һ": "h", "і": "i",
})


def normalize_name(name: str) -> str:
    text = _PUNCT.sub(" ", name.lower())
    text = _GENERIC.sub(" ", text)
    return " ".join(text.split())


def name_score(a: str, b: str) -> float:
    """0-100. Compares transliterated names; a name fully contained in the other
    ("Хива" in "Хива, Астана") counts if the shorter one has >= 4 letters."""
    ta, tb = normalize_name(a).translate(_TRANSLIT), normalize_name(b).translate(_TRANSLIT)
    if not ta or not tb:
        return 0.0
    score = fuzz.ratio(ta, tb)
    if min(len(ta), len(tb)) >= 4:
        score = max(score, fuzz.token_set_ratio(ta, tb))
    return score


M_PER_DEG_LAT = 111_320


def plan_cells(
    pois: list[dict],
    cell_m: float = 1000,
    max_per_cell: int = 20,
    min_cell_m: float = 250,
    cap: int = 300,
) -> list[dict]:
    """Square grid over the POIs; a cell with > max_per_cell POIs is split in 4
    (down to min_cell_m). Each cell -> one search circle around its center.
    Raises ValueError if the plan needs more than `cap` calls."""
    if not pois:
        return []
    lat0 = sum(p["lat"] for p in pois) / len(pois)
    m_per_deg_lon = M_PER_DEG_LAT * math.cos(math.radians(lat0))
    pts = [(p["lon"] * m_per_deg_lon, p["lat"] * M_PER_DEG_LAT) for p in pois]

    def split(x0: float, y0: float, size: float, members: list) -> list[tuple]:
        if len(members) <= max_per_cell or size / 2 < min_cell_m:
            return [(x0, y0, size)]
        half = size / 2
        out = []
        for dx in (0, half):
            for dy in (0, half):
                sub = [(x, y) for x, y in members if x0 + dx <= x < x0 + dx + half and y0 + dy <= y < y0 + dy + half]
                if sub:
                    out += split(x0 + dx, y0 + dy, half, sub)
        return out

    buckets: dict[tuple[int, int], list] = {}
    for x, y in pts:
        buckets.setdefault((math.floor(x / cell_m), math.floor(y / cell_m)), []).append((x, y))

    squares = []
    for (i, j), members in buckets.items():
        squares += split(i * cell_m, j * cell_m, cell_m, members)
    if len(squares) > cap:
        raise ValueError(f"plan needs {len(squares)} calls > cap {cap}")

    return [
        {
            "lat": (y0 + size / 2) / M_PER_DEG_LAT,
            "lon": (x0 + size / 2) / m_per_deg_lon,
            "radius_m": round(size / math.sqrt(2) + 5),
        }
        for x0, y0, size in squares
    ]


def match(pois: list[dict], places: list[dict]) -> dict[str, dict]:
    """Pair each OSM POI with at most one Google place (and vice versa).

    A pair needs distance < MAX_DISTANCE_M and name score >= MIN_NAME_SCORE;
    conflicts are resolved greedily by best (score, -distance).
    """
    candidates = []
    for poi in pois:
        if not normalize_name(poi["name"]):
            continue
        for pl in places:
            d = haversine_m(poi["lat"], poi["lon"], pl["lat"], pl["lon"])
            if d >= MAX_DISTANCE_M:
                continue
            score = name_score(poi["name"], pl["name"])
            if score >= MIN_NAME_SCORE:
                candidates.append((score, -d, poi["poi_id"], pl["id"]))

    out: dict[str, dict] = {}
    used: set[str] = set()
    for score, neg_d, poi_id, pid in sorted(candidates, reverse=True):
        if poi_id in out or pid in used:
            continue
        out[poi_id] = {"google_place_id": pid, "match_score": round(score), "distance_m": round(-neg_d)}
        used.add(pid)
    return out


def load_popular_pois() -> list[dict]:
    raw = json.loads(latest_raw("osm_").read_text(encoding="utf-8"))
    out = []
    for e in raw["elements"]:
        tags = e.get("tags", {})
        name = tags.get("name")
        lat = e.get("lat", e.get("center", {}).get("lat"))
        lon = e.get("lon", e.get("center", {}).get("lon"))
        if not name or lat is None:
            continue
        if any(tags.get(k) in vals for k, vals in OSM_POPULAR.items()):
            out.append({"poi_id": f"osm_{e['type']}_{e['id']}", "name": name, "lat": lat, "lon": lon})
    return out


def _cached_post(body: dict, key: str, stats: dict) -> dict:
    payload = json.dumps(body, sort_keys=True)
    path = CACHE_DIR / "places" / f"{hashlib.sha1(payload.encode()).hexdigest()}.json"
    if path.exists():
        stats["cache_hits"] += 1
        return json.loads(path.read_text(encoding="utf-8"))
    if stats["calls"] >= MAX_CALLS:
        raise RuntimeError(f"call cap {MAX_CALLS} reached; stopping")
    resp = requests.post(
        NEARBY_URL,
        data=payload,
        headers={"Content-Type": "application/json", "X-Goog-Api-Key": key, "X-Goog-FieldMask": FIELD_MASK},
        timeout=20,
    )
    stats["calls"] += 1
    if resp.status_code != 200:
        raise RuntimeError(f"Places API HTTP {resp.status_code}: {resp.text[:300]}")
    data = resp.json()
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")
    time.sleep(0.1)
    return data


def main() -> None:
    ap = argparse.ArgumentParser(description="A3: match OSM POI to Google place_id")
    ap.add_argument("--dry-run", action="store_true", help="print planned calls, send nothing")
    args = ap.parse_args()

    pois = load_popular_pois()
    cells = plan_cells(pois, cap=MAX_CALLS // len(TYPE_GROUPS))
    planned = len(cells) * len(TYPE_GROUPS)
    print(f"[enrich] {len(pois)} popular POI -> {len(cells)} cells x {len(TYPE_GROUPS)} groups = {planned} calls (cap {MAX_CALLS})")
    if args.dry_run:
        return

    load_dotenv()
    key = os.getenv("GOOGLE_PLACES_API_KEY")
    if not key:
        print("[enrich] GOOGLE_PLACES_API_KEY not set -> skipping enrichment (snapshot stays OSM-only)")
        return

    stats = {"calls": 0, "cache_hits": 0}
    places: dict[str, dict] = {}
    stopped: str | None = None
    for cell in cells:
        if stopped:
            break
        for types in TYPE_GROUPS.values():
            body = {
                "includedTypes": types,
                "maxResultCount": 20,
                "rankPreference": "DISTANCE",
                "languageCode": "ru",
                "locationRestriction": {"circle": {
                    "center": {"latitude": round(cell["lat"], 6), "longitude": round(cell["lon"], 6)},
                    "radius": float(cell["radius_m"]),
                }},
            }
            try:
                data = _cached_post(body, key, stats)
            except RuntimeError as err:  # quota / cap / HTTP error: keep what we have
                stopped = str(err)[:200]
                print(f"[enrich] stopped early: {stopped}", file=sys.stderr)
                break
            for p in data.get("places", []):
                places[p["id"]] = {
                    "id": p["id"],
                    "name": p.get("displayName", {}).get("text", ""),
                    "lat": p["location"]["latitude"],
                    "lon": p["location"]["longitude"],
                }

    matches = match(pois, list(places.values()))
    now = datetime.now(timezone.utc)
    out = RAW_DIR / f"places_{now:%Y%m%d}.json"
    out.write_text(json.dumps({
        "_meta": {
            "collected_at": now.isoformat(timespec="seconds"),
            "source": "google_places_new",
            "api_calls": stats["calls"],
            "cache_hits": stats["cache_hits"],
            "google_places_seen": len(places),
            "popular_osm_poi": len(pois),
            "complete": stopped is None,
            "stopped_reason": stopped,
            "note": "Only place_id + match quality stored (Google Maps Platform ToS).",
        },
        "matches": matches,
    }, ensure_ascii=False, indent=1), encoding="utf-8")
    pct = 100 * len(matches) / max(len(pois), 1)
    print(f"[enrich] calls={stats['calls']} cache_hits={stats['cache_hits']} google={len(places)} "
          f"matched {len(matches)}/{len(pois)} ({pct:.0f}%) -> data/raw/{out.name}"
          + ("" if stopped is None else "  [PARTIAL: re-run after quota reset; cached calls are free]"))


if __name__ == "__main__":
    try:
        main()
    except RuntimeError as err:
        print(f"[enrich] {err}", file=sys.stderr)
        sys.exit(1)
