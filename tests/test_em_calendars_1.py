"""Calendars BR, ZA, PL, CZ and HU (app/calendars/rules/), against published lists (docs/phase-4.md, step 2d)."""

from datetime import date

import pytest

from app.calendars import rules, service


def _days(name: str) -> dict[date, str]:
    return {d.day: d.holiday for d in rules.parse(rules.read(f"repo:{name}.json")).days}


BR, ZA, PL, CZ, HU = _days("br"), _days("za"), _days("pl"), _days("cz"), _days("hu")


def _weekdays(days: dict, y: int) -> list[str]:
    return [f"{d:%m-%d}" for d in sorted(days) if d.year == y and d.weekday() < 5]


@pytest.mark.parametrize(("name", "first"), [("br", 1990), ("za", 1995), ("pl", 1990), ("cz", 1990), ("hu", 1990)])
def test_years(name, first):
    assert rules.parse(rules.read(f"repo:{name}.json")).years == tuple(range(first, 2101))


def test_registered():
    for c in ("BR", "ZA", "PL", "CZ", "HU"):
        assert service.CALENDARS[c].source_names[-1] == f"{c}-RULES"
    assert service.SOURCES["BR-ANBIMA"].parse is None  # kept raw until its parser is written against a real capture


def test_br_is_anbimas_tables():
    # ANBIMA's 2026 table, less November 15 (a Sunday), and 2023's and 2024's: Black Consciousness Day from 2024.
    assert _weekdays(BR, 2026) == [
        "01-01", "02-16", "02-17", "04-03", "04-21", "05-01", "06-04", "09-07", "10-12", "11-02", "11-20", "12-25"]
    assert date(2023, 11, 20) not in BR and BR[date(2024, 11, 20)] == "Black Consciousness Day"
    # 2001's, less April 21 (a Saturday).
    assert _weekdays(BR, 2001) == [
        "01-01", "02-26", "02-27", "04-13", "05-01", "06-14", "09-07", "10-12", "11-02", "11-15", "12-25"]


def test_za_is_the_published_lists():
    # The weekdays of 2024's list (Freedom Day a Saturday; Youth Day a Sunday, so Monday June 17) and 2026's.
    assert _weekdays(ZA, 2024) == ["01-01", "03-21", "03-29", "04-01", "05-01", "05-29", "06-17", "08-09", "09-24", "12-16", "12-25",
                                   "12-26"]
    assert _weekdays(ZA, 2026) == ["01-01", "04-03", "04-06", "04-27", "05-01", "06-16", "08-10", "09-24", "11-04", "12-16",
                                   "12-25"]


def test_za_christmas_on_a_sunday_is_declared_not_automatic():
    assert ZA[date(2022, 12, 26)].startswith("Day of Goodwill") and date(2022, 12, 27) in ZA  # declared
    assert date(2005, 12, 27) not in ZA and date(2033, 12, 27) not in ZA


def test_pl_is_the_nbps_fixings():
    assert _weekdays(PL, 2024) == ["01-01", "04-01", "05-01", "05-03", "05-30", "08-15", "11-01", "11-11", "12-25", "12-26"]
    assert _weekdays(PL, 2026) == ["01-01", "01-06", "04-06", "05-01", "06-04", "11-11", "12-24", "12-25"]
    assert date(2018, 11, 12) not in PL and date(2010, 1, 6) not in PL


def test_cz_is_the_cnbs_fixings():
    assert _weekdays(CZ, 2024) == ["01-01", "03-29", "04-01", "05-01", "05-08", "07-05", "10-28", "12-24", "12-25", "12-26"]
    assert _weekdays(CZ, 2026) == ["01-01", "04-03", "04-06", "05-01", "05-08", "07-06", "09-28", "10-28", "11-17", "12-24",
                                   "12-25"]
    assert date(2015, 4, 3) not in CZ and date(1991, 5, 9) in CZ and date(1991, 5, 8) not in CZ


def test_hu_is_the_mnbs_fixings_with_bridge_days():
    assert _weekdays(HU, 2024) == ["01-01", "03-15", "03-29", "04-01", "05-01", "05-20", "08-19", "08-20", "10-23", "11-01",
                                   "12-24", "12-25", "12-26", "12-27"]
    assert _weekdays(HU, 2026) == ["01-01", "01-02", "04-03", "04-06", "05-01", "05-25", "08-20", "08-21", "10-23", "12-24",
                                   "12-25"]
    assert date(1992, 6, 8) not in HU and date(1993, 5, 31) in HU  # Whit Monday from 1993
