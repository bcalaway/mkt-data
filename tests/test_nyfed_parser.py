"""FED-NYFED-<year>: the NY Fed's holiday-schedule circulars, 2003-2009.

Fixtures are the hub's captures, byte for byte (capture-export, 2026-10-04):
captures #15 (2009), #16 (2008), #18 (2007), #19 (2006), #20 (2005), #21 (2004)
and #22 (2003). SHA-256 prefixes in CAPTURES.
"""

import hashlib
from datetime import date

import pytest

from app.calendars import nyfed, rules
from app.calendars.parsed import ParseError
from tests.conftest import FIXTURES

CAPTURES = {  # year: (capture id, SHA-256 prefix)
    2003: (22, "161818d0e92b6bdd"),
    2004: (21, "f45ecd92875c1517"),
    2005: (20, "49cd0a55fc2e441f"),
    2006: (19, "ff3101e4828027cc"),
    2007: (18, "442596336c5ed97c"),
    2008: (16, "db281b4f30a48f16"),
    2009: (15, "840ab468bf6af1ee"),
}


def _circular(year: int) -> bytes:
    cid, sha = CAPTURES[year]
    body = (FIXTURES / f"nyfed_circular_{year}_capture{cid}.html").read_bytes()
    assert hashlib.sha256(body).hexdigest().startswith(sha)
    return body


@pytest.mark.parametrize("year", sorted(CAPTURES))
def test_each_circular_matches_fed_rules(year):
    """The cross-check, pinned: every circular agrees with FED-RULES day for day."""
    p = nyfed.parse(_circular(year))
    assert p.years == (year,)
    expected = {d for d in rules.parse(rules.read("repo:fed.json")).days if d.day.year == year}
    assert set(p.days) == expected


def test_the_wrinkles():
    by_day = {d.day: d for y in CAPTURES for d in nyfed.parse(_circular(y)).days}
    # 2004 lists Independence Day on its observed Monday.
    assert by_day[date(2004, 7, 5)].holiday == "Independence Day (observed)"
    # Saturday holidays close nothing: the Banks stay open the Friday before.
    assert date(2004, 12, 24) not in by_day and date(2009, 7, 3) not in by_day
    # Sunday holidays move to the Monday the note names.
    assert by_day[date(2005, 12, 26)].holiday == "Christmas Day (observed)"
    assert by_day[date(2006, 1, 2)].holiday == "New Year's Day (observed)"
    assert by_day[date(2007, 11, 12)].holiday == "Veterans Day (observed)"
    # Presidents' Day is FED-RULES' "Washington's Birthday", in every wording.
    assert by_day[date(2003, 2, 17)].holiday == by_day[date(2009, 2, 16)].holiday == "Washington's Birthday"


def _page(rows: str, year: int = 2006) -> bytes:
    return (
        "<p>All offices of the Federal Reserve Bank of New York are closed on all Saturdays and Sundays "
        f"and for the following holiday observances in the year {year}:</p>{rows}<p>Bank's Holiday Schedule</p>"
    ).encode()


TEN_2006 = "".join(
    f"<p>{n}</p><p>{d}</p>" for n, d in [
        ("New Year's Day", "Sun, Jan 1"), ("Birthday of Martin Luther King, Jr.", "Mon, Jan 16"),
        ("Presidents' Day", "Mon, Feb 20"), ("Memorial Day", "Mon, May 29"), ("Independence Day", "Tue, July 4"),
        ("Labor Day", "Mon, Sep 4"), ("Columbus Day", "Mon, Oct 9"), ("Veterans Day", "Sat, Nov 11"),
        ("Thanksgiving Day", "Thu, Nov 23"), ("Christmas Day", "Mon, Dec 25"),
    ]
)


def test_a_sunday_without_its_note_fails():
    with pytest.raises(ParseError, match="no note"):
        nyfed.parse(_page(TEN_2006))


def test_a_missing_holiday_fails():
    nine = TEN_2006.replace("<p>Labor Day</p><p>Mon, Sep 4</p>", "")
    with pytest.raises(ParseError, match="expected 10"):
        nyfed.parse(_page(nine))


def test_a_wrong_weekday_fails():
    with pytest.raises(ParseError, match="not a"):
        nyfed.parse(_page(TEN_2006.replace("Mon, Sep 4", "Tue, Sep 4")))
