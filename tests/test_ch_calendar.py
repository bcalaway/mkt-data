"""Calendar CH: SIC's banking holidays (app/calendars/rules/ch.json), against SIX's published lists."""

from datetime import date

import pytest

from app.calendars import rules, service, six_sic
from app.calendars.parsed import ParseError
from tests.conftest import FIXTURES

SPEC = rules.parse(rules.read("repo:ch.json"))
DAYS = {d.day: d.holiday for d in SPEC.days}


def _year(y: int) -> list[date]:
    return sorted(d for d in DAYS if d.year == y)


def test_years_and_sources():
    assert SPEC.years == tuple(range(1990, 2101))
    assert service.CALENDARS["CH"].source_names == ["SIX-SIC", "CH-RULES"]


def test_2027_is_sixs_list():
    # SIX's SIC banking holidays for 2027: Jan 2, May 1, Aug 1, Dec 25 and 26 fall on weekends and aren't moved.
    assert _year(2027) == [date(2027, 1, 1), date(2027, 3, 26), date(2027, 3, 29), date(2027, 5, 6),
                           date(2027, 5, 17)]


def test_2026_is_the_published_list():
    # feiertagskalender.ch's 2026 SIC list ("gemäss SIX"); August 1 and December 26 are Saturdays.
    assert _year(2026) == [date(2026, 1, 1), date(2026, 1, 2), date(2026, 4, 3), date(2026, 4, 6), date(2026, 5, 1),
                           date(2026, 5, 14), date(2026, 5, 25), date(2026, 12, 25)]


def test_eves_are_clearing_days_and_national_day_from_1994():
    assert date(2026, 12, 24) not in DAYS and date(2026, 12, 31) not in DAYS
    assert date(1990, 8, 1) not in DAYS and DAYS[date(1994, 8, 1)] == "Swiss National Day"


def test_ascension_on_labour_day_is_one_day():
    assert DAYS[date(2008, 5, 1)] == "Labour Day and Ascension Day"


SIX = (FIXTURES / "six_sic_banking_holidays_capture8327.pdf").read_bytes()  # the hub's first capture, 2026-10-08


def test_sixs_pdf_covers_its_year_and_closes_weekdays_marked_no():
    p = six_sic.parse(SIX)
    assert p.years == (2027,)  # Dec 2026 and Jan 2028 rows belong to the neighbouring lists
    assert [(d.day, d.holiday) for d in p.days] == [
        (date(2027, 1, 1), "New Year's Day"), (date(2027, 3, 26), "Good Friday"), (date(2027, 3, 29), "Easter Monday"),
        (date(2027, 5, 6), "Ascension Day"), (date(2027, 5, 17), "Whit Monday"),
    ]
    assert {d.day for d in p.days} == set(_year(2027))  # the rules agree


HEAD = "The schedule of clearing days for SIC ... during bank holidays in 2027 has been determined\n"
ROWS = [
    "Thursday 24 December 2026 Christmas Eve Yes Yes", "Friday 1 January 2027 New Year\u2019s Day No No",
    "Saturday 2 January 2027 Berchtold\u2018s Day No No", "Friday 26 March 2027 Good Friday No No",
    "Monday 29 March 2027 Easter Monday No No", "Saturday 1 May 2027 Labor Day No No",
    "Thursday 6 May 2027 Ascension Day No Yes", "Monday 17 May 2027 Whit Monday No Yes",
    "Sunday 1 August 2027 Swiss National Day No No", "Friday 24 December 2027 Christmas Eve Yes Yes",
    "Saturday 25 December 2027 Christmas Day No No", "Sunday 26 December 2027 St. Stephen\u2019s Day No No",
    "Friday 31 December 2027 New Year\u2019s Eve Yes Yes",
]


@pytest.mark.parametrize(("rows", "message"), [
    (ROWS[:6], "fewer than 10"),
    ([*ROWS, "Friday 26 March 2027 Good Friday Maybe No"], "can't read"),
    ([*ROWS, "Monday 26 March 2027 Good Friday No No"], "isn't a Monday"),
    ([*ROWS, "Friday 26 March 2027 Good Friday No No"], "listed twice"),
])
def test_parse_refuses_what_it_doesnt_understand(monkeypatch, rows, message):
    monkeypatch.setattr(six_sic, "_text", lambda _: HEAD + "\n".join(rows))
    with pytest.raises(ParseError, match=message):
        six_sic.parse(b"")


def test_no_heading_raises(monkeypatch):
    monkeypatch.setattr(six_sic, "_text", lambda _: "\n".join(ROWS))
    with pytest.raises(ParseError, match="heading"):
        six_sic.parse(b"")


def test_apostrophes_are_plain(monkeypatch):
    monkeypatch.setattr(six_sic, "_text", lambda _: HEAD + "\n".join(ROWS))
    assert six_sic.parse(b"").days[0].holiday == "New Year's Day"
