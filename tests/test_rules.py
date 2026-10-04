"""Rule sets and cited exceptions (app/calendars/rules.py and rules/*.json)."""

import json
from datetime import date, time

import pytest

from app.calendars import fed, rules
from app.calendars.parsed import Day, ParseError


def _fed_rules(**changes) -> dict:
    return json.loads(rules.read("repo:fed.json")) | changes


def _parse(spec: dict):
    return rules.parse(json.dumps(spec).encode())


# --- FED-RULES (repo:fed.json)


def test_fed_rules_cover_1986_to_2025():
    p = rules.parse(rules.read("repo:fed.json"))
    assert p.years == tuple(range(1986, 2026))
    assert len(p.days) == 382
    assert all(d.status == "closed" and d.day.weekday() < 5 for d in p.days)


def test_fed_rules_reproduce_k8_exactly(fed_html):
    # The same rules over K.8's years give K.8's table, names and observed days included.
    assert _parse(_fed_rules(first_year=2026, last_year=2030)) == fed.parse(fed_html)


# The NY Fed's yearly holiday circulars (11465, 11532, 11615, 11720, 11797,
# 11879, 11980): the weekdays each year's Reserve Banks closed.
CIRCULARS = {
    2003: ["01-01", "01-20", "02-17", "05-26", "07-04", "09-01", "10-13", "11-11", "11-27", "12-25"],
    2004: ["01-01", "01-19", "02-16", "05-31", "07-05", "09-06", "10-11", "11-11", "11-25"],
    2005: ["01-17", "02-21", "05-30", "07-04", "09-05", "10-10", "11-11", "11-24", "12-26"],
    2006: ["01-02", "01-16", "02-20", "05-29", "07-04", "09-04", "10-09", "11-23", "12-25"],
    2007: ["01-01", "01-15", "02-19", "05-28", "07-04", "09-03", "10-08", "11-12", "11-22", "12-25"],
    2008: ["01-01", "01-21", "02-18", "05-26", "07-04", "09-01", "10-13", "11-11", "11-27", "12-25"],
    2009: ["01-01", "01-19", "02-16", "05-25", "09-07", "10-12", "11-11", "11-26", "12-25"],
}


@pytest.mark.parametrize("year", sorted(CIRCULARS))
def test_fed_rules_match_the_ny_fed_circulars(year):
    days = {d.day for d in rules.parse(rules.read("repo:fed.json")).days if d.day.year == year}
    assert days == {date.fromisoformat(f"{year}-{md}") for md in CIRCULARS[year]}


def test_fed_rules_edges():
    days = {d.day: d for d in rules.parse(rules.read("repo:fed.json")).days}
    assert days[date(1986, 1, 20)].holiday == "Birthday of Martin Luther King, Jr."  # first MLK Day
    assert date(2021, 6, 18) not in days  # Juneteenth 2021 fell on a Saturday: no weekday closed
    assert days[date(2022, 6, 20)] == Day(date(2022, 6, 20), "closed", "Juneteenth National Independence Day (observed)")
    assert date(2010, 12, 31) not in days  # New Year's 2011 on a Saturday: open the Friday before


# --- SIFMA-US-EXCEPTIONS (repo:sifma_us_exceptions.json)


def test_sifma_exceptions():
    p = rules.parse(rules.read("repo:sifma_us_exceptions.json"))
    assert p.years == ()  # adds dates, covers no year
    assert p.days == (
        Day(date(2025, 1, 9), "early_close", "National Day of Mourning (President Carter) (early close)", time(14)),
    )


# --- The engine


def test_observance_and_nth_weekday_rules():
    spec = {
        "calendar": "X", "first_year": 2027, "last_year": 2027,
        "observance": {"saturday": "friday", "sunday": "monday"},
        "holidays": [
            {"name": "Independence Day", "month": 7, "day": 4},  # a Sunday in 2027
            {"name": "Christmas Day", "month": 12, "day": 25},  # a Saturday
            {"name": "New Year's Day", "month": 1, "day": 1, "observance": {"saturday": "none"}},
            {"name": "Memorial Day", "month": 5, "weekday": "monday", "n": -1},
            {"name": "Thanksgiving Day", "month": 11, "weekday": "thursday", "n": 4},
        ],
    }
    days = {d.day: d.holiday for d in _parse(spec).days}
    assert days == {
        date(2027, 1, 1): "New Year's Day",
        date(2027, 5, 31): "Memorial Day",
        date(2027, 7, 5): "Independence Day (observed)",
        date(2027, 11, 25): "Thanksgiving Day",
        date(2027, 12, 24): "Christmas Day (observed)",
    }


def test_open_exception_removes_a_rule_day():
    spec = _fed_rules(exceptions=[{"date": "2025-12-25", "status": "open", "citation": "https://example.org/x"}])
    assert date(2025, 12, 25) not in {d.day for d in _parse(spec).days}


@pytest.mark.parametrize(
    ("exception", "message"),
    [
        ({"date": "2025-01-09", "status": "closed", "holiday": "X"}, "citation"),
        ({"date": "2025-01-11", "status": "closed", "holiday": "X", "citation": "https://e.org"}, "weekend"),
        ({"date": "2025-01-09", "status": "early_close", "holiday": "X", "citation": "https://e.org"}, "close_time"),
        ({"date": "2025-01-09", "status": "maybe", "holiday": "X", "citation": "https://e.org"}, "status"),
        ({"date": "2025-01-08", "status": "open", "citation": "https://e.org"}, "rules don't close"),
        ({"date": "January 9", "status": "closed", "holiday": "X", "citation": "https://e.org"}, "valid 'date'"),
    ],
)
def test_bad_exceptions_fail(exception, message):
    with pytest.raises(ParseError, match=message):
        _parse(_fed_rules(exceptions=[exception]))


def test_bad_files_fail():
    with pytest.raises(ParseError, match="valid JSON"):
        rules.parse(b"{not json")
    with pytest.raises(ParseError, match="calendar"):
        _parse({"first_year": 2020, "last_year": 2021})
    with pytest.raises(ParseError, match="year range"):
        _parse({"calendar": "X", "first_year": 2021})
    with pytest.raises(ParseError, match="'weekday' and 'n'"):
        _parse({"calendar": "X", "first_year": 2021, "last_year": 2021, "holidays": [{"name": "Y", "month": 1}]})


def test_read_only_reads_files_in_the_rules_folder():
    assert rules.read("repo:fed.json").startswith(b"{")
    for name in ("repo:../rules.py", "repo:nope.json", "repo:"):
        with pytest.raises(FileNotFoundError):
            rules.read(name)
