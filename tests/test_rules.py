"""Rule sets and cited exceptions (app/calendars/rules.py and rules/*.json)."""

import json
from datetime import date, time

import pytest

from app.calendars import fed, nyse, rules
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
        Day(date(2001, 9, 11), "closed", "September 11 attacks", None),
        Day(date(2001, 9, 12), "closed", "September 11 attacks", None),
        Day(date(2004, 6, 11), "closed", "National Day of Mourning (President Reagan)", None),
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


UK_CHRISTMAS = {
    "calendar": "X", "first_year": 2010, "last_year": 2022,
    "observance": {"saturday": "monday", "sunday": "monday", "collision": "next"},
    "holidays": [{"name": "Christmas Day", "month": 12, "day": 25}, {"name": "Boxing Day", "month": 12, "day": 26}],
}


def test_substitute_days_move_to_the_next_free_weekday():
    days = {d.day: d.holiday for d in _parse(UK_CHRISTMAS).days if d.day.year in (2010, 2016, 2021, 2022)}
    assert days == {
        # Saturday and Sunday: Monday, then the Tuesday (gov.uk's 2021: Dec 27 and 28 substitute days).
        date(2010, 12, 27): "Christmas Day (observed)", date(2010, 12, 28): "Boxing Day (observed)",
        date(2021, 12, 27): "Christmas Day (observed)", date(2021, 12, 28): "Boxing Day (observed)",
        # Sunday and Monday: Boxing Day keeps its Monday, Christmas moves to the Tuesday (gov.uk's 2022).
        date(2016, 12, 26): "Boxing Day", date(2016, 12, 27): "Christmas Day (observed)",
        date(2022, 12, 26): "Boxing Day", date(2022, 12, 27): "Christmas Day (observed)",
    }


def test_without_collision_next_two_holidays_on_a_day_fail():
    spec = UK_CHRISTMAS | {"observance": {"saturday": "monday", "sunday": "monday"}}
    with pytest.raises(ParseError, match="two holidays close 2010-12-27"):
        _parse(spec)


def test_collision_share_makes_two_holidays_one_day():
    spec = {
        "calendar": "X", "first_year": 2008, "last_year": 2008,
        "observance": {"saturday": "none", "sunday": "none", "collision": "share"},
        "holidays": [{"name": "Labour Day", "month": 5, "day": 1}, {"name": "Ascension Day", "easter": 39}],
    }
    assert [(d.day, d.holiday) for d in _parse(spec).days] == [(date(2008, 5, 1), "Labour Day and Ascension Day")]


def test_weekday_relative_to_a_date_and_date_tables():
    spec = {
        "calendar": "X", "first_year": 2024, "last_year": 2026,
        "holidays": [
            # Victoria Day: the Monday on or before May 24 (May 20, 2024; May 19, 2025; May 18, 2026).
            {"name": "Victoria Day", "month": 5, "day": 24, "weekday": "monday", "match": "on_or_before"},
            # Wellington Anniversary: the Monday nearest January 22 (Jan 22, 2024; Jan 20, 2025; Jan 19, 2026).
            {"name": "Wellington Anniversary Day", "month": 1, "day": 22, "weekday": "monday", "match": "nearest"},
            {"name": "Matariki", "dates": {"2024": "06-28", "2025": "06-20", "2026": "07-10"}},
            {"name": "Later", "month": 3, "day": 1, "weekday": "friday", "match": "on_or_after", "from": 2026},
        ],
    }
    assert sorted(d.day for d in _parse(spec).days) == [
        date(2024, 1, 22), date(2024, 5, 20), date(2024, 6, 28),
        date(2025, 1, 20), date(2025, 5, 19), date(2025, 6, 20),
        date(2026, 1, 19), date(2026, 3, 6), date(2026, 5, 18), date(2026, 7, 10),
    ]
    with pytest.raises(ParseError, match="'match' needs"):
        _parse(spec | {"holidays": [{"name": "Bad", "month": 5, "day": 24, "match": "closest", "weekday": "monday"}]})


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


# --- NYSE-RULES (repo:nyse.json)


def test_nyse_rules_cover_1990_to_2025():
    p = rules.parse(rules.read("repo:nyse.json"))
    assert p.years == tuple(range(1990, 2026))
    assert (len(p.days), sum(d.status == "early_close" for d in p.days)) == (406, 80)


def test_nyse_rules_reproduce_the_hours_page_exactly(nyse_html):
    spec = json.loads(rules.read("repo:nyse.json")) | {"first_year": 2026, "last_year": 2028, "exceptions": []}
    assert _parse(spec) == nyse.parse(nyse_html)


# ICE's announcement of the 2023-2025 holiday and early-close calendar.
ICE_2023_2025 = {
    "closed": [
        "2023-01-02", "2023-01-16", "2023-02-20", "2023-04-07", "2023-05-29", "2023-06-19", "2023-07-04",
        "2023-09-04", "2023-11-23", "2023-12-25", "2024-01-01", "2024-01-15", "2024-02-19", "2024-03-29",
        "2024-05-27", "2024-06-19", "2024-07-04", "2024-09-02", "2024-11-28", "2024-12-25", "2025-01-01",
        "2025-01-20", "2025-02-17", "2025-04-18", "2025-05-26", "2025-06-19", "2025-07-04", "2025-09-01",
        "2025-11-27", "2025-12-25",
        "2025-01-09",  # announced later: Carter's day of mourning
    ],
    "early_close": [
        "2023-07-03", "2023-11-24", "2024-07-03", "2024-11-29", "2024-12-24", "2025-07-03", "2025-11-28",
        "2025-12-24",
    ],
}


def test_nyse_rules_match_ice_2023_to_2025():
    days = rules.parse(rules.read("repo:nyse.json")).days
    for status, expected in ICE_2023_2025.items():
        got = {d.day for d in days if 2023 <= d.day.year <= 2025 and d.status == status}
        assert got == {date.fromisoformat(x) for x in expected}, status


def test_nyse_rules_history():
    days = {d.day: d for d in rules.parse(rules.read("repo:nyse.json")).days}
    assert date(1997, 1, 20) not in days and days[date(1998, 1, 19)].holiday == "Martin Luther King, Jr. Day"
    assert date(2021, 6, 18) not in days and date(2022, 6, 20) in days  # Juneteenth from 2022
    assert date(1999, 12, 31) in days and days[date(1999, 12, 31)].close_time == time(13)
    assert date(2010, 12, 31) not in days  # Saturday New Year's Day: no Friday holiday
    assert days[date(1993, 12, 24)] == Day(date(1993, 12, 24), "closed", "Christmas Day (observed)")
    assert date(1996, 7, 3) not in days and days[date(1996, 7, 5)].close_time == time(13)
    assert days[date(1992, 11, 27)].close_time == time(14) and days[date(1993, 11, 26)].close_time == time(13)
    assert days[date(1990, 12, 24)].close_time == time(14) and date(1991, 7, 3) not in days


def test_easter():
    assert [rules.easter(y) for y in (1990, 2000, 2015, 2019, 2024, 2027)] == [
        date(1990, 4, 15), date(2000, 4, 23), date(2015, 4, 5), date(2019, 4, 21), date(2024, 3, 31), date(2027, 3, 28),
    ]


def test_early_close_rules_only_apply_on_their_weekdays():
    spec = {
        "calendar": "X", "first_year": 2024, "last_year": 2025,
        "holidays": [{"name": "Eve (early close)", "month": 12, "day": 24, "weekdays": ["tuesday"],
                      "status": "early_close", "close_time": "13:00"}],
    }
    assert _parse(spec).days == (Day(date(2024, 12, 24), "early_close", "Eve (early close)", time(13)),)
    spec["holidays"][0]["weekdays"] = ["saturday"]
    with pytest.raises(ParseError, match="Monday to Friday"):
        _parse(spec)


# --- Projections (rules/*_projected.json)


@pytest.mark.parametrize("name", ["fed_projected.json", "sifma_us_projected.json", "nyse_projected.json"])
def test_projections_cover_2026_to_2100_with_full_closes_only(name):
    p = rules.parse(rules.read(f"repo:{name}"))
    assert p.years == tuple(range(2026, 2101))
    assert {d.status for d in p.days} == {"closed"} and all(d.day.weekday() < 5 for d in p.days)


def test_fed_projection_uses_the_same_rules_and_reproduces_k8(fed_html):
    proj, hist = (json.loads(rules.read(f"repo:{f}")) for f in ("fed_projected.json", "fed.json"))
    assert proj["holidays"] == hist["holidays"] and proj["observance"] == hist["observance"]
    assert _parse(proj | {"last_year": 2030}) == fed.parse(fed_html)


def test_nyse_projection_has_the_full_closes_of_the_hours_page(nyse_html):
    proj, hist = (json.loads(rules.read(f"repo:{f}")) for f in ("nyse_projected.json", "nyse.json"))
    assert proj["holidays"] == [h for h in hist["holidays"] if h.get("status", "closed") == "closed"]
    closed = {d for d in nyse.parse(nyse_html).days if d.status == "closed"}
    assert set(_parse(proj | {"last_year": 2028}).days) == closed


def test_sifma_projection_matches_sifmas_record_1996_to_2026():
    from app.calendars import sifma, sifma_history
    from tests.conftest import FIXTURES

    published = {}  # lowest precedence first, so higher sources overwrite
    for parsed in (
        sifma_history.parse((FIXTURES / "sifma_us_history_1996_2019.pdf").read_bytes()),
        sifma.parse_archive((FIXTURES / "sifma_us_archive.html").read_bytes()),
        sifma.parse((FIXTURES / "sifma_us_2026.html").read_bytes()),
    ):
        published |= {d.day: d for d in parsed.days}
    closed = {d for d, x in published.items() if x.status == "closed" and 1996 <= d.year <= 2026}
    spec = json.loads(rules.read("repo:sifma_us_projected.json")) | {"first_year": 1996}
    projected = {d.day for d in _parse(spec | {"last_year": 2026}).days}
    # One-off closes can't be projected.
    assert closed - projected == {date(2012, 10, 30), date(2018, 12, 5)}
    # Good Fridays SIFMA turned into early closes (jobs-report years; 11 a.m. in 2007).
    assert projected - closed == {
        date(1999, 4, 2), date(2007, 4, 6), date(2010, 4, 2), date(2012, 4, 6), date(2015, 4, 3),
        date(2021, 4, 2), date(2023, 4, 7), date(2026, 4, 3),
    }
    assert all(published[d].status == "early_close" for d in projected - closed)
