"""SIFMA's 1996-2019 PDF, against the real capture (#5, tests/fixtures)."""

from collections import Counter
from datetime import date, time

import pytest

from app.calendars import sifma_history
from app.calendars.parsed import Day, ParseError


@pytest.fixture(scope="module")
def parsed():
    from tests.conftest import FIXTURES

    return sifma_history.parse((FIXTURES / "sifma_us_history_1996_2019.pdf").read_bytes())


@pytest.fixture(scope="module")
def days(parsed):
    return {d.day: d for d in parsed.days}


def test_covers_1996_to_2019(parsed):
    assert parsed.years == tuple(range(1996, 2020))
    assert len(parsed.days) == 473
    assert max(d.day for d in parsed.days) == date(2020, 1, 1)  # stored, but 2020 isn't covered


def test_full_and_early_closes_per_year(parsed):
    count = Counter((d.day.year, d.status) for d in parsed.days)
    per_year = {y: (count[(y, "closed")], count[(y, "early_close")]) for y in range(1996, 2020)}
    assert per_year == {
        1996: (11, 12), 1997: (11, 12), 1998: (11, 11), 1999: (10, 12), 2000: (9, 11),
        2001: (11, 12), 2002: (11, 12), 2003: (11, 12), 2004: (11, 12), 2005: (10, 12),
        2006: (10, 11), 2007: (10, 12), 2008: (11, 12), 2009: (11, 7), 2010: (10, 4),
        2011: (10, 5), 2012: (11, 6), 2013: (11, 5), 2014: (11, 6), 2015: (11, 6),
        2016: (11, 6), 2017: (10, 6), 2018: (12, 6), 2019: (11, 6),
    }


def test_two_early_closes_in_one_cell(days):
    # "Wednesday, July 3; Friday, July 5" around July 4, 1996.
    assert days[date(1996, 7, 3)] == Day(date(1996, 7, 3), "early_close", "U.S. Independence Day (early close)", time(14))
    assert days[date(1996, 7, 5)].close_time == time(14)
    assert days[date(1996, 7, 4)] == Day(date(1996, 7, 4), "closed", "U.S. Independence Day")


def test_close_times_in_parentheses(days):
    assert days[date(1999, 4, 1)].close_time == time(14)  # "(2pm EST)"
    assert days[date(1999, 4, 2)].close_time == time(12)  # "(noon EST)", and no full close
    assert days[date(1999, 12, 31)].close_time == time(13)  # "(1:00 pm EST)"
    assert days[date(2007, 4, 6)].close_time == time(11)  # "(11:00 am EST early close)"
    assert days[date(2010, 4, 2)].close_time == time(12)  # "(Early 12:00pm close)"


def test_abbreviated_months_and_missing_commas(days):
    assert days[date(1999, 1, 18)].holiday == "Martin Luther King Day"  # "Monday Jan. 18"
    assert days[date(1999, 9, 3)].status == "early_close"  # "Friday, Sept. 3"


def test_no_recommendation_cells(days):
    assert date(2000, 11, 10) not in days  # Veterans Day 2000: "NA" (a Saturday holiday)
    assert date(2005, 12, 31) not in days  # "None (holiday falls on Saturday)"
    assert days[date(1999, 12, 24)].status == "closed"  # Christmas 1999 observed on Friday


def test_cross_referenced_new_years_entries_agree(days):
    # The 2003 table lists "(Friday, January 2, 2004)" and the 2004 table "Friday, January 2, 2004".
    assert days[date(2004, 1, 2)] == Day(date(2004, 1, 2), "early_close", "New Year's Day (early close)", time(14))
    assert days[date(2003, 12, 31)].status == "early_close"


def test_unscheduled_closes(days):
    assert days[date(2012, 10, 29)] == Day(date(2012, 10, 29), "early_close", "Hurricane Sandy (early close)", time(12))
    assert days[date(2012, 10, 30)] == Day(date(2012, 10, 30), "closed", "Hurricane Sandy")
    assert days[date(2018, 12, 5)] == Day(date(2018, 12, 5), "closed", "Former President George H.W. Bush")


def test_names_match_the_other_sifma_sources(parsed):
    names = {d.holiday.removesuffix(" (early close)") for d in parsed.days}
    assert names == {
        "New Year's Day", "Martin Luther King Day", "Presidents Day", "Good Friday", "Memorial Day",
        "U.S. Independence Day", "Labor Day", "Columbus Day", "Veterans Day", "Thanksgiving Day",
        "Christmas Day", "Hurricane Sandy", "Former President George H.W. Bush",
    }


def test_typos_are_corrected(days):
    # Printed as "Friday, December 30, 2015" (2016 table) and "Friday, December 31, 2016" (2017 table).
    assert days[date(2016, 12, 30)] == Day(date(2016, 12, 30), "early_close", "New Year's Day (early close)", time(14))
    assert date(2015, 12, 30) not in days


def test_without_the_corrections_the_typos_fail(monkeypatch):
    from tests.conftest import FIXTURES

    monkeypatch.setattr(sifma_history, "CORRECTIONS", {})
    with pytest.raises(ParseError, match="2015-12-30 is a Wednesday, not a Friday"):
        sifma_history.parse((FIXTURES / "sifma_us_history_1996_2019.pdf").read_bytes())


def test_entries():
    e = sifma_history._entries
    assert e("Wednesday, December 31, 1997", 1997, "New Year's Day", True) == [(date(1997, 12, 31), time(14))]
    assert e("NA", 2000, "Veterans Day", False) == []
    assert e("Monday, December 26 (observed)", 2005, "Christmas Day", False) == [(date(2005, 12, 26), None)]
    with pytest.raises(ParseError, match="can't read"):
        e("Friday, July 5 (tentative)", 1996, "U.S. Independence Day", True)
    with pytest.raises(ParseError, match="no date"):
        e("see notice", 1996, "Labor Day", False)
    with pytest.raises(ParseError, match="a time in the full-close column"):
        e("Friday, April 2 (noon EST)", 1999, "Good Friday", False)


def test_not_a_pdf():
    with pytest.raises(ParseError, match="not a readable PDF"):
        sifma_history.parse(b"<html>not a pdf</html>")
