"""Calendar CH: SIC's banking holidays (app/calendars/rules/ch.json), against SIX's published lists."""

from datetime import date

from app.calendars import rules, service

SPEC = rules.parse(rules.read("repo:ch.json"))
DAYS = {d.day: d.holiday for d in SPEC.days}


def _year(y: int) -> list[date]:
    return sorted(d for d in DAYS if d.year == y)


def test_years_and_sources():
    assert SPEC.years == tuple(range(1990, 2101))
    assert service.CALENDARS["CH"].source_names == ["SIX-SIC", "CH-RULES"]
    assert service.SOURCES["SIX-SIC"].parse is None  # kept raw until its parser is written against a real capture


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
