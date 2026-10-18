"""A2: parse OSM opening_hours into a weekly structure; open/closed/unknown at a moment."""

import re
from datetime import datetime, timedelta, timezone

ASTANA_TZ = timezone(timedelta(hours=5))  # Asia/Almaty, UTC+5 since 2024

DAYS = ["mo", "tu", "we", "th", "fr", "sa", "su"]

_DAY = r"(?:Mo|Tu|We|Th|Fr|Sa|Su|PH)"
_DAYSPEC = rf"{_DAY}(?:-{_DAY})?(?:\s*,\s*{_DAY}(?:-{_DAY})?)*"
_SPAN = r"\d{1,2}:\d{2}\s*-\s*\d{1,2}:\d{2}"
_RULE = re.compile(rf"(?P<days>{_DAYSPEC})?\s*(?P<times>off|closed|{_SPAN}(?:\s*,\s*{_SPAN})*)", re.I)
_SEPARATORS = re.compile(r"^[\s;,]*$")


def _minutes(hhmm: str) -> int:
    h, m = hhmm.split(":")
    return int(h) * 60 + int(m)


def _expand_days(spec: str | None) -> list[str]:
    if not spec:
        return list(DAYS)
    out: list[str] = []
    for part in re.split(r"\s*,\s*", spec.lower()):
        if part == "ph":  # public holidays: ignored
            continue
        if "-" in part:
            a, b = (DAYS.index(x) for x in part.split("-"))
            out += [DAYS[(a + k) % 7] for k in range((b - a) % 7 + 1)]
        else:
            out.append(part)
    return out


def parse_hours(raw: str | None) -> dict | None:
    """OSM opening_hours -> {"mo": [["09:00","18:00"], ...], ...}; None if not understood."""
    if not raw or not raw.strip():
        return None
    text = raw.strip()
    if text == "24/7":
        return {d: [["00:00", "24:00"]] for d in DAYS}
    week: dict[str, list[list[str]]] = {d: [] for d in DAYS}
    pos = 0
    seen_day_rule = False
    for m in _RULE.finditer(text):
        if not _SEPARATORS.match(text[pos : m.start()]):
            return None  # unparsed garbage between rules
        pos = m.end()
        days = m["days"]
        if days and all(d.strip().lower() == "ph" for d in days.split(",")):
            return None  # holiday-only rule ("PH off"): we don't know today's holidays -> unknown
        if not days and seen_day_rule:
            return None  # "Mo-Sa ...; off": ambiguous override of all days -> unknown
        seen_day_rule = seen_day_rule or bool(days)
        times = m["times"].lower()
        spans = [] if times in ("off", "closed") else [re.split(r"\s*-\s*", s) for s in re.split(r"\s*,\s*", times)]
        for d in _expand_days(m["days"]):
            week[d] = [list(s) for s in spans]  # later rule overrides the day
    if pos == 0 or not _SEPARATORS.match(text[pos:]):
        return None
    return week


def open_status(raw: str | None, now: datetime) -> str:
    week = parse_hours(raw)
    if week is None:
        return "unknown"
    if now.tzinfo is not None:
        now = now.astimezone(ASTANA_TZ)
    t = now.hour * 60 + now.minute
    today = now.weekday()
    for start, end in week[DAYS[today]]:
        s, e = _minutes(start), _minutes(end)
        if e <= s:  # runs past midnight
            e += 24 * 60
        if s <= t < e:
            return "open"
    # yesterday's ranges that spill past midnight into today
    for start, end in week[DAYS[(today - 1) % 7]]:
        s, e = _minutes(start), _minutes(end)
        if e <= s and t < e:
            return "open"
    return "closed"
