from datetime import datetime, timedelta, timezone

import pytest

from pipeline.hours import open_status, parse_hours

ALMATY = timezone(timedelta(hours=5))


def at(day: int, hh: int, mm: int = 0) -> datetime:
    """day: 0=Mon ... 6=Sun, in the week of 2026-10-12 (Mon)."""
    return datetime(2026, 10, 12 + day, hh, mm, tzinfo=ALMATY)


def test_simple_daily_range_is_open_inside_and_closed_outside():
    assert open_status("Mo-Su 10:00-22:00", at(5, 12)) == "open"
    assert open_status("Mo-Su 10:00-22:00", at(5, 23)) == "closed"


def test_range_past_midnight_carries_into_next_morning():
    # Friday's 12:00-02:00 is still running at Saturday 01:00
    assert open_status("Mo-Fr 12:00-02:00", at(5, 1)) == "open"
    assert open_status("Mo-Fr 12:00-02:00", at(5, 3)) == "closed"
    assert open_status("Mo-Su 08:00-24:00", at(2, 23, 59)) == "open"


def test_multiple_rules_day_lists_and_off():
    bar = "Fr-Sa 12:00-03:00; Mo-Th,Su 12:00-02:00"
    assert open_status(bar, at(6, 2, 30)) == "open"  # Saturday night spill
    assert open_status(bar, at(0, 2, 30)) == "closed"  # Sunday ends 02:00
    office = "Mo-Fr 09:00-18:00; Sa 10:00-16:00; Su off"
    assert open_status(office, at(5, 15)) == "open"
    assert open_status(office, at(6, 12)) == "closed"


def test_day_range_wrapping_over_the_week_end():
    assert open_status("Su-Th 10:00-22:00", at(0, 12)) == "open"  # Monday
    assert open_status("Su-Th 10:00-22:00", at(4, 12)) == "closed"  # Friday
    assert open_status("We-Mo 10:00-20:00", at(1, 12)) == "closed"  # Tuesday


def test_always_open_and_bare_times_mean_every_day():
    assert open_status("24/7", at(3, 4)) == "open"
    assert open_status("09:00-06:00", at(6, 5)) == "open"
    assert open_status("09:00-06:00", at(6, 7)) == "closed"


# 10 typical formats seen in Astana OSM data -> spot-checked days
TYPICAL = [
    ("24/7", {"mo": [["00:00", "24:00"]], "su": [["00:00", "24:00"]]}),
    ("09:00-06:00", {"mo": [["09:00", "06:00"]], "sa": [["09:00", "06:00"]]}),
    ("Mo-Su 12:00-01:00", {"we": [["12:00", "01:00"]], "su": [["12:00", "01:00"]]}),
    ("Mo-Fr 08:00-00:00; Sa-Su 09:00-00:00", {"fr": [["08:00", "00:00"]], "sa": [["09:00", "00:00"]]}),
    ("Fr-Sa 12:00-03:00; Mo-Th,Su 12:00-02:00", {"th": [["12:00", "02:00"]], "fr": [["12:00", "03:00"]], "su": [["12:00", "02:00"]]}),
    ("Mo-Su,PH 10:00-22:00", {"mo": [["10:00", "22:00"]], "su": [["10:00", "22:00"]]}),
    ("Mo-Fr 09:00-18:00; Sa 10:00-16:00; Su off", {"tu": [["09:00", "18:00"]], "sa": [["10:00", "16:00"]], "su": []}),
    ("Mo-Fr 09:00-18:00, Sa-Su 10:00-16:00", {"mo": [["09:00", "18:00"]], "su": [["10:00", "16:00"]]}),
    ("Mo-Su 10:00-14:00,15:00-20:00", {"we": [["10:00", "14:00"], ["15:00", "20:00"]]}),
    ("Mo-Fr 09:00-18:00; Fr,Sa off", {"th": [["09:00", "18:00"]], "fr": [], "sa": [], "su": []}),
    ("12:00 - 06:00", {"tu": [["12:00", "06:00"]]}),
]


@pytest.mark.parametrize("raw,expected_days", TYPICAL)
def test_parse_hours_typical_astana_formats(raw, expected_days):
    week = parse_hours(raw)
    assert week is not None
    for day, spans in expected_days.items():
        assert week[day] == spans


def test_missing_or_unparseable_hours_are_unknown_never_open():
    for raw in [None, "", "по договорённости", "Mo-Fr 9-18", "sunrise-sunset"]:
        assert open_status(raw, at(2, 12)) == "unknown"


def test_holiday_and_ambiguous_rules_are_unknown_not_guessed():
    assert open_status("Mo-Fr 09:00-18:00; PH off", at(2, 12)) == "unknown"
    assert open_status("Mo-Sa 08:00-20:00; off", at(2, 12)) == "unknown"
    assert open_status("Mo-Su,PH 10:00-22:00", at(2, 12)) == "open"  # PH with the same hours is fine


def test_utc_time_is_converted_to_astana_time():
    # 07:00 UTC = 12:00 in Astana (UTC+5)
    assert open_status("Mo-Su 10:00-14:00", datetime(2026, 10, 14, 7, 0, tzinfo=timezone.utc)) == "open"
