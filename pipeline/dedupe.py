"""A6: OSM elements -> clean POI records: one category, mood tags, flags, dedupe.

Mapping follows docs (yerlan.md section 5 / TA appendix B).
"""

import re
from datetime import date

CATEGORIES = ["coffee", "food", "park", "kids", "culture", "viewpoint", "shopping",
              "sport", "night", "unusual", "library", "cowork"]
INDOOR = {"coffee", "food", "culture", "shopping", "library", "cowork", "night"}

# (osm key, values) -> (category, extra tags); first match wins
_RULES: list[tuple[str, set[str], str, list[str]]] = [
    ("amenity", {"bar", "pub", "nightclub", "hookah_lounge"}, "night", []),
    ("amenity", {"cafe"}, "coffee", []),
    ("amenity", {"restaurant", "food_court", "ice_cream"}, "food", []),
    ("amenity", {"library"}, "library", ["тихо", "розетки", "бесплатно"]),
    ("amenity", {"coworking_space"}, "cowork", ["розетки", "wi-fi", "тихо"]),
    ("office", {"coworking"}, "cowork", ["розетки", "wi-fi", "тихо"]),
    ("amenity", {"planetarium"}, "unusual", []),
    ("leisure", {"escape_game"}, "unusual", ["крытое"]),
    ("amenity", {"theatre", "cinema", "arts_centre"}, "culture", []),
    ("tourism", {"museum", "gallery"}, "culture", []),
    ("tourism", {"zoo", "aquarium", "theme_park"}, "kids", []),
    ("tourism", {"attraction", "viewpoint", "artwork"}, "viewpoint", ["фото"]),
    ("historic", set(), "viewpoint", ["история"]),  # any historic=*
    ("leisure", {"park", "garden", "nature_reserve"}, "park", ["на воздухе"]),
    ("leisure", {"playground", "water_park"}, "kids", []),
    ("leisure", {"ice_rink", "fitness_centre", "sports_centre"}, "sport", []),
    ("shop", {"mall"}, "shopping", ["крытое"]),
]
_UNUSUAL = re.compile(r"лофт|крыш|\bарт\b|арт-|loft|roof|\bart\b", re.I)
# Cyrillic letters that look Latin ("Sayajay аrt" is typed with a Cyrillic "а")
_HOMOGLYPHS = str.maketrans("аеорсхук", "aeopcxyk")


def _category(tags: dict) -> tuple[str, list[str]] | None:
    for key, values, cat, extra in _RULES:
        v = tags.get(key)
        if v is not None and (not values or v in values):
            return cat, list(extra)
    return None


def _mood_tags(tags: dict, category: str) -> list[str]:
    out = []
    if tags.get("internet_access") in ("wlan", "yes", "wifi"):
        out.append("wi-fi")
    if tags.get("outdoor_seating") == "yes":
        out.append("терраса")
    if tags.get("fee") == "no":
        out.append("бесплатно")
    if tags.get("cuisine") and "coffee" in tags["cuisine"]:
        out.append("кофе")
    hours = tags.get("opening_hours", "")
    if hours == "24/7" or any(f"-{h}:" in hours for h in ("23", "24", "00", "01", "02", "03", "04", "05", "06")):
        out.append("ночью")
    if category in INDOOR:
        out.append("крытое")
    return out


def to_poi(el: dict, today: date | None = None) -> dict | None:
    """One OSM element -> POI record, or None if it is not one of our categories."""
    tags = el.get("tags", {})
    found = _category(tags)
    if found is None:
        return None
    category, tag_list = found
    name = (tags.get("name") or "").strip()
    low = name.lower()
    if category in ("viewpoint", "culture") and (_UNUSUAL.search(low) or _UNUSUAL.search(low.translate(_HOMOGLYPHS))):
        category = "unusual"

    lat = el.get("lat", el.get("center", {}).get("lat"))
    lon = el.get("lon", el.get("center", {}).get("lon"))
    tag_list += [t for t in _mood_tags(tags, category) if t not in tag_list]
    wheelchair = tags.get("wheelchair")
    hours = tags.get("opening_hours")

    return {
        "poi_id": f"osm_{el['type']}_{el['id']}",
        "name": name,
        "name_kk": tags.get("name:kk"),
        "name_en": tags.get("name:en"),
        "lat": lat,
        "lon": lon,
        "category": category,
        "tags": tag_list,
        "opening_hours_raw": hours,
        "hours_source": "osm" if hours else None,
        "phone": tags.get("phone") or tags.get("contact:phone"),
        "website": tags.get("website") or tags.get("contact:website"),
        "wikidata": tags.get("wikidata"),
        "wheelchair": wheelchair if wheelchair in ("yes", "limited", "no") else "unknown",
        "kid_friendly": category in ("kids", "park"),
        "adult_only": category == "night",
        "indoor": category in INDOOR,
        "sources": ["osm"],
        "last_checked": (today or date.today()).isoformat(),
    }


DUPLICATE_M = 30
# Unnamed objects that are still useful get a plain generic name; others are dropped.
_GENERIC_NAMES = {"kids": "Детская площадка", "park": "Сквер", "sport": "Спортивная площадка"}


def _richness(p: dict) -> int:
    fields = ("name_kk", "name_en", "opening_hours_raw", "phone", "website", "wikidata")
    return sum(1 for f in fields if p.get(f)) + len(p["tags"]) + (p["wheelchair"] != "unknown")


def _is_junk(name: str) -> bool:
    letters = sum(ch.isalpha() for ch in name)
    return letters < 2


def dedupe(records: list[dict]) -> tuple[list[dict], list[dict]]:
    """-> (kept, dropped[{poi_id, name, reason}]); reasons: no_coords, no_name, junk_name, duplicate.
    Duplicates = similar name within DUPLICATE_M; the record with more data is kept."""
    from pipeline.enrich import MIN_NAME_SCORE, haversine_m, name_score

    dropped: list[dict] = []
    candidates: list[dict] = []
    for p in records:
        reason = None
        if p["lat"] is None or p["lon"] is None:
            reason = "no_coords"
        elif not p["name"]:
            if p["category"] in _GENERIC_NAMES:
                p = {**p, "name": _GENERIC_NAMES[p["category"]], "name_generic": True}
            else:
                reason = "no_name"
        elif _is_junk(p["name"]):
            reason = "junk_name"
        if reason:
            dropped.append({"poi_id": p["poi_id"], "name": p["name"], "reason": reason})
        else:
            candidates.append(p)

    kept: list[dict] = []
    for p in sorted(candidates, key=_richness, reverse=True):
        dup = next((k for k in kept
                    if k["category"] == p["category"]
                    and haversine_m(k["lat"], k["lon"], p["lat"], p["lon"]) < DUPLICATE_M
                    and name_score(k["name"], p["name"]) >= MIN_NAME_SCORE), None)
        if dup:
            dropped.append({"poi_id": p["poi_id"], "name": p["name"], "reason": "duplicate", "kept": dup["poi_id"]})
        else:
            kept.append(p)
    return kept, dropped
