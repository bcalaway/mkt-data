"""NYSE-HISTORY: the History of New York Stock Exchange Holidays PDF.

The fixture is the hub's capture #17 byte for byte (capture-export,
2026-10-04; SHA-256 cbebd12230d3600a...): the "Revised through January 2011"
copy.
"""

import hashlib
from datetime import date, time

import pytest

from app.calendars import nyse_history, rules
from app.calendars.parsed import Day, ParseError
from tests.conftest import FIXTURES


@pytest.fixture(scope="module")
def history():
    body = (FIXTURES / "nyse_history_capture17.pdf").read_bytes()
    assert hashlib.sha256(body).hexdigest().startswith("cbebd12230d3600a")
    return nyse_history.parse(body)


def test_covers_no_years_only_its_special_closings(history):
    assert history.years == ()
    assert len(history.days) == 55
    assert min(d.day for d in history.days).year == 1990 and max(d.day for d in history.days).year == 2010


def test_matches_nyse_rules_except_one_halt(history):
    """The cross-check, pinned: 54 of 55 match NYSE-RULES exactly, and every
    special day in the rules (1990-2010) is in the history. The one addition is
    June 1, 2005, a systems halt at 3:56 pm after which trading didn't resume,
    treated like the 1997 circuit-breaker halt the rules already have."""
    ours = {d.day: d for d in history.days}
    theirs = {d.day: d for d in rules.parse(rules.read("repo:nyse.json")).days if 1990 <= d.day.year <= 2010}
    assert {day for day, d in ours.items() if theirs.get(day) != d} == {date(2005, 6, 1)}
    assert ours[date(2005, 6, 1)] == Day(date(2005, 6, 1), "early_close", "Systems halt (early close)", time(15, 56))
    special = {
        day for day, d in theirs.items()
        if d.status == "early_close" or not any(
            d.holiday.startswith(h) for h in (
                "New Year's Day", "Martin Luther King", "Washington's Birthday", "Good Friday", "Memorial Day",
                "Independence Day", "Labor Day", "Thanksgiving Day", "Christmas Day",
            )
        )
    }
    assert special <= set(ours)


def test_the_edge_cases(history):
    ours = {d.day: d for d in history.days}
    assert all(ours[date(2001, 9, d)].holiday == "September 11 attacks" for d in (11, 12, 13, 14))  # a range
    assert ours[date(1990, 12, 24)].close_time == time(14)  # "Christmas Eve. Closed at 2:00 pm."
    assert ours[date(1996, 1, 8)].close_time == time(14)  # "Trading floor closed at 2:00 pm" on a continuation line
    assert ours[date(1997, 10, 27)].close_time == time(15, 30)  # circuit breakers
    assert date(2009, 7, 2) not in ours  # closed at 4:15 pm: late, not early
    assert date(2001, 9, 17) not in ours and date(2003, 9, 11) not in ours  # reopening, moments of silence
    assert date(2005, 4, 8) not in ours  # a footnoted moment of silence


HEADER = ["NEW YORK STOCK EXCHANGE SPECIAL CLOSINGS, 1885–date"]


def test_a_close_with_an_unknown_reason_fails():
    with pytest.raises(ParseError, match="no known reason"):
        nyse_history.parse_lines(HEADER + ["Mar. 3, 2008 (Mon) Closed for a reason nobody listed."])


def test_an_entry_about_closing_that_isnt_understood_fails():
    with pytest.raises(ParseError, match="can't tell"):
        nyse_history.parse_lines(HEADER + ["Mar. 3, 2008 (Mon) The floor will close early, details later."])


def test_a_wrong_weekday_fails():
    with pytest.raises(ParseError, match="weekday"):
        nyse_history.parse_lines(HEADER + ["Nov. 26, 2010 (Thu) Closed at 1:00 pm. Day after Thanksgiving Day."])


def test_years_outside_1990_2010_are_ignored():
    p = nyse_history.parse_lines(HEADER + [
        "Aug. 9, 1976 (Mon) Floor closed at 3:00 pm. Hurricane watch.",
        "Nov. 26, 2010 (Fri) Closed at 1:00 pm. Day after Thanksgiving Day.",
    ])
    assert [d.day for d in p.days] == [date(2010, 11, 26)]
