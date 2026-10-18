"""Conservative subset of OSM hours. Unsupported syntax stays unknown."""

import re
from datetime import timedelta

from .geo import ALMATY
from .schemas import OpenStatus

DAYS = ["Mo", "Tu", "We", "Th", "Fr", "Sa", "Su"]


def _days(text):
    if not text:
        return set(range(7))
    result = set()
    for part in text.split(","):
        bits = part.split("-")
        if any(b not in DAYS for b in bits) or len(bits) > 2:
            raise ValueError("unsupported_day")
        start, end = DAYS.index(bits[0]), DAYS.index(bits[-1])
        result.update((start + i) % 7 for i in range((end - start) % 7 + 1))
    return result


def _minutes(text):
    h, m = map(int, text.split(":"))
    if not (0 <= h <= 24 and 0 <= m <= 59) or (h == 24 and m != 0):
        raise ValueError("unsupported_time")
    return 60 * h + m


def schedule_open(raw, now):
    raw = raw.strip().replace("–", "-").replace("—", "-")
    if raw in ("24/7", "круглосуточно"):
        return True
    raw = re.sub(r"^(ежедневно|Daily|daily)\s+", "", raw)
    raw = re.sub(r"(\d{1,2}:\d{2})\s*-\s*(\d{1,2}:\d{2})", r"\1-\2", raw)
    day = r"(?:Mo|Tu|We|Th|Fr|Sa|Su|PH)"
    raw = re.sub(rf"(?<=\d{{2}}),\s*(?={day})", "; ", raw)
    raw = re.sub(rf",\s+(?={day})", ",", raw)
    rules = []
    for clause in raw.split(";"):
        clause = clause.strip()
        if "PH" in clause:
            prefix, _, hours = clause.partition(" ")
            regular = ",".join(d for d in prefix.split(",") if d != "PH")
            # Only ignore PH when it has exactly the same hours as every weekday.
            if _days(regular) != set(range(7)) or not regular:
                raise ValueError("holiday_hours_unconfirmed")
            clause = regular + " " + hours
        match = re.fullmatch(
            r"\s*(?:(Mo|Tu|We|Th|Fr|Sa|Su)([A-Za-z,\-]*)\s+)?(off|closed|\d{1,2}:\d{2}-\d{1,2}:\d{2}(?:\s*,\s*\d{1,2}:\d{2}-\d{1,2}:\d{2})*)\s*",
            clause,
        )
        if not match:
            raise ValueError("unsupported_hours")
        days = _days((match[1] or "") + (match[2] or ""))
        ranges = (
            []
            if match[3] in ("off", "closed")
            else [tuple(_minutes(t) for t in pair.strip().split("-")) for pair in match[3].split(",")]
        )
        rules.append((days, ranges))
    minute = now.hour * 60 + now.minute
    day, yesterday = now.weekday(), (now - timedelta(days=1)).weekday()
    today_ranges = next((ranges for days, ranges in reversed(rules) if day in days), None)
    previous_ranges = next((ranges for days, ranges in reversed(rules) if yesterday in days), [])
    if today_ranges == []:
        return False
    today_open = any((start <= minute < end if end > start else minute >= start) for start, end in today_ranges or [])
    overnight = any(end <= start and minute < end for start, end in previous_ranges)
    return today_open or overnight


def open_status(poi, now):
    now = now.astimezone(ALMATY)
    base = dict(hours=poi.opening_hours_raw, source=poi.hours_source, checked_at=poi.last_checked)
    if not poi.opening_hours_raw or poi.hours_source == "none":
        return OpenStatus(state="unknown", confidence="low", **base)
    try:
        opened = schedule_open(poi.opening_hours_raw, now)
    except ValueError:
        return OpenStatus(state="unknown", confidence="low", **base)
    fresh = poi.last_checked is not None and 0 <= (now.date() - poi.last_checked).days <= 30 and not poi.hours_conflict
    state = ("open" if fresh else "likely_open") if opened else "closed"
    return OpenStatus(state=state, confidence="high" if fresh else "medium", **base)
