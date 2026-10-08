"""Calendar GB: gov.uk's bank holidays JSON (app/calendars/govuk.py) and the rules for 1990-2018."""

import json
from datetime import date

import pytest

from app.calendars import govuk, rules
from app.calendars.parsed import ParseError

EVENTS_2021 = [  # gov.uk's England and Wales 2021, as published (2021-12-27/28 substitute days)
    ("New Year’s Day", "2021-01-01", ""), ("Good Friday", "2021-04-02", ""), ("Easter Monday", "2021-04-05", ""),
    ("Early May bank holiday", "2021-05-03", ""), ("Spring bank holiday", "2021-05-31", ""),
    ("Summer bank holiday", "2021-08-30", ""), ("Christmas Day", "2021-12-27", "Substitute day"),
    ("Boxing Day", "2021-12-28", "Substitute day"),
]


def _doc(events) -> bytes:
    ev = [{"title": t, "date": d, "notes": n, "bunting": True} for t, d, n in events]
    return json.dumps({"england-and-wales": {"division": "england-and-wales", "events": ev},
                       "scotland": {"division": "scotland", "events": []}}).encode()


def test_parse_reads_england_and_wales():
    p = govuk.parse(_doc(EVENTS_2021))
    assert p.years == (2021,)
    assert [(d.day, d.holiday) for d in p.days][-2:] == [
        (date(2021, 12, 27), "Christmas Day (substitute day)"), (date(2021, 12, 28), "Boxing Day (substitute day)")]


@pytest.mark.parametrize(("events", "message"), [
    (EVENTS_2021[:5], "fewer than the 8"),
    ([*EVENTS_2021, ("Odd", "2021-12-25", "")], "weekend day"),
    ([*EVENTS_2021, ("Again", "2021-01-01", "")], "listed twice"),
])
def test_parse_refuses_what_it_doesnt_understand(events, message):
    with pytest.raises(ParseError, match=message):
        govuk.parse(_doc(events))
    with pytest.raises(ParseError, match="no england-and-wales"):
        govuk.parse(b'{"scotland": {}}')


def _gb(years: range) -> dict[date, str]:
    spec = json.loads(rules.read("repo:gb.json"))
    spec |= {"first_year": years.start, "last_year": years.stop - 1,
             "exceptions": [x for x in spec["exceptions"] if int(x["date"][:4]) in years]}
    return {d.day: d.holiday for d in rules.parse(json.dumps(spec).encode()).days}


def test_rules_reproduce_govuks_2021():
    assert sorted(_gb(range(2021, 2022))) == [date.fromisoformat(d) for _, d, _ in EVENTS_2021]


def test_rules_history():
    days = _gb(range(1990, 2019))
    assert len(rules.parse(rules.read("repo:gb.json")).years) == 29
    assert date(1995, 5, 1) not in days and days[date(1995, 5, 8)] == "Early May bank holiday (VE Day)"
    assert days[date(1999, 12, 31)] == "Millennium bank holiday" and days[date(2000, 1, 3)] == "New Year's Day (observed)"
    assert date(2002, 5, 27) not in days and {date(2002, 6, 3), date(2002, 6, 4)} <= set(days)
    assert days[date(2011, 4, 29)] == "Royal wedding bank holiday"
    assert date(2012, 5, 28) not in days and {date(2012, 6, 4), date(2012, 6, 5)} <= set(days)
    # Sunday Christmas, Monday Boxing Day: Boxing Day keeps its Monday, Christmas moves to the Tuesday.
    assert days[date(2016, 12, 26)] == "Boxing Day" and days[date(2016, 12, 27)] == "Christmas Day (observed)"
    assert sum(1 for d in days if d.year == 2003) == 8
