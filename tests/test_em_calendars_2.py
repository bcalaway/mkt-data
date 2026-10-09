"""Calendars CL, IL, TR, HK, CN, SG, TH and ID (app/calendars/rules/), against published lists (docs/phase-4.md,
step 2d). Their holidays follow lunar or announced dates, so each file covers only the years published."""

from datetime import date, time

import pytest

from app.calendars import rules, service

NAMES = ("cl", "il", "tr", "hk", "cn", "sg", "th", "id")


def _parsed(name: str):
    return rules.parse(rules.read(f"repo:{name}.json"))


def _days(name: str) -> dict:
    return {d.day: d for d in _parsed(name).days}


def _weekdays(days: dict, y: int, status: str = "closed") -> list[str]:
    return [f"{d:%m-%d}" for d in sorted(days) if d.year == y and d.weekday() < 5 and days[d].status == status]


@pytest.mark.parametrize(("name", "first", "last"), [
    ("cl", 2005, 2026), ("il", 2005, 2027), ("tr", 2005, 2027), ("hk", 2008, 2027), ("cn", 2008, 2026),
    ("sg", 2010, 2027), ("th", 2019, 2027), ("id", 2010, 2027)])
def test_years(name, first, last):
    assert _parsed(name).years == tuple(range(first, last + 1))


@pytest.mark.projections
def test_registered():
    for c in NAMES:
        assert service.CALENDARS[c.upper()].source_names == [f"{c.upper()}-RULES", f"{c.upper()}-PROJECTED"]


def test_cl():
    days = _days("cl")
    # Peter and Paul moved to Monday June 29; the indigenous day on Sunday June 21; the banks' December 31.
    assert _weekdays(days, 2026) == ["01-01", "04-03", "05-01", "05-21", "06-29", "07-16", "09-18", "10-12", "12-08",
                                     "12-25", "12-31"]


def test_il_counts_fridays_and_election_days():
    days = _days("il")
    assert _weekdays(days, 2026) == ["03-03", "04-02", "04-08", "04-22", "05-22", "07-23", "09-21", "10-27"]
    assert date(2026, 5, 22).weekday() == 4  # Shavuot, a Friday: Zahav runs Sunday to Friday


def test_tr_eves_are_half_days():
    days = _days("tr")
    assert _weekdays(days, 2026) == ["01-01", "03-20", "04-23", "05-01", "05-19", "05-27", "05-28", "05-29", "07-15",
                                     "10-29"]
    assert _weekdays(days, 2026, "early_close") == ["03-19", "05-26", "10-28"]
    assert days[date(2026, 3, 19)].close_time == time(13, 0)
    # Kurban Bayrami 2006-12-31 to 2007-01-03, across the year end.
    assert all(date(2007, 1, d) in days for d in (1, 2, 3))


def test_hk_is_the_gazetted_list():
    days = _days("hk")
    # GovHK's 2023 list (published 2022-05-13), weekdays only: no October 3.
    assert _weekdays(days, 2023) == ["01-02", "01-23", "01-24", "01-25", "04-05", "04-07", "04-10", "05-01", "05-26",
                                     "06-22", "10-02", "10-23", "12-25", "12-26"]
    assert date(2015, 9, 3) in days  # the one-off general holiday


def test_cn_is_the_state_councils_notice():
    # The 2026 notice: New Year January 1-3, Spring Festival February 15-23, Qingming April 4-6, Labour Day May 1-5,
    # Dragon Boat June 19-21, Mid-Autumn September 25-27, National Day October 1-7; weekdays only.
    assert _weekdays(_days("cn"), 2026) == [
        "01-01", "01-02", "02-16", "02-17", "02-18", "02-19", "02-20", "02-23", "04-06", "05-01", "05-04", "05-05",
        "06-19", "09-25", "10-01", "10-02", "10-05", "10-06", "10-07"]


def test_sg_moves_sunday_holidays_to_the_next_free_weekday():
    days = _days("sg")
    assert _weekdays(days, 2026) == ["01-01", "02-17", "02-18", "04-03", "05-01", "05-27", "06-01", "08-10", "11-09",
                                     "12-25"]
    assert date(2023, 1, 23) in days and date(2023, 1, 24) in days  # Chinese New Year on Sunday and Monday


def test_th_is_the_bank_of_thailands_list():
    days = _days("th")
    assert date(2019, 5, 6) in days  # the coronation special holiday
    assert len(_weekdays(days, 2026)) == 20


def test_id_includes_cuti_bersama():
    days = _days("id")
    # Idul Fitri 2025 (March 31 and April 1) with its cuti bersama days around it.
    assert {"03-28", "03-31", "04-01", "04-02", "04-03", "04-04", "04-07"} <= set(_weekdays(days, 2025))
