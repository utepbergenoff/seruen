"""Build frontend/night-lights.json for the dark map's "open now" lights.

For every place in data/poi.json with opening hours the server can read, store one bit per half hour of the
week (Monday 00:00 first): 1 = open by the server's own schedule parser (backend/hours.py). The browser lights a
place only when its bit for the current half hour is 1. Places without hours, or with hours the parser rejects,
are left out, so nothing is ever shown as open on a guess.

usage: python scripts/build_night_lights.py
"""
import json
import sys
from datetime import datetime, timedelta
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from backend.geo import ALMATY  # noqa: E402
from backend.hours import schedule_open  # noqa: E402

MONDAY = datetime(2026, 10, 19, tzinfo=ALMATY)  # any Monday: only the weekday and the time matter
SLOTS = 7 * 48


def week_mask(raw):
    """84 hex characters, 4 half-hour slots each; the middle of each slot is checked."""
    bits = [schedule_open(raw, MONDAY + timedelta(minutes=30 * i + 15)) for i in range(SLOTS)]
    return "".join(f"{int(''.join('1' if b else '0' for b in bits[i:i + 4]), 2):x}" for i in range(0, SLOTS, 4))


def main():
    places, skipped = [], 0
    for p in json.loads((ROOT / "data/poi.json").read_text(encoding="utf-8")):
        raw = (p.get("opening_hours_raw") or "").strip()
        if not raw or p.get("hours_source") == "none":
            continue
        try:
            mask = week_mask(raw)
        except ValueError:
            skipped += 1
            continue
        if set(mask) == {"0"}:
            continue
        places.append({"id": p["poi_id"], "name": p["name"], "name_kk": p.get("name_kk"), "name_en": p.get("name_en"),
                       "category": p["category"], "lat": round(p["lat"], 5), "lon": round(p["lon"], 5),
                       "hours": raw, "source": p.get("hours_source"), "checked": p.get("last_checked"), "week": mask})
    out = {"slot_min": 30, "week_starts": "Mo 00:00 Asia/Almaty", "places": places}
    (ROOT / "frontend/night-lights.json").write_text(json.dumps(out, ensure_ascii=False, separators=(",", ":")), encoding="utf-8")
    print(f"{len(places)} places with readable hours, {skipped} with hours the parser cannot read (left out)")


if __name__ == "__main__":
    main()
