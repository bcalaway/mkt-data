"""Calendar TARGET: the ECB's closing days (app/calendars/rules/target.json)."""

from datetime import date

from app.calendars import rules

DAYS = {d.day: d.holiday for d in rules.parse(rules.read("repo:target.json")).days}


def test_years():
    assert rules.parse(rules.read("repo:target.json")).years == tuple(range(1999, 2101))


def test_1999_to_2001():
    # 1999: only New Year (Jan 1, a Friday), Christmas (a Saturday, so no weekday) and 31 December.
    assert sorted(d for d in DAYS if d.year == 1999) == [date(1999, 1, 1), date(1999, 12, 31)]
    assert date(1999, 4, 2) not in DAYS  # Good Friday 1999: open
    # 2000: the standing set; 2001 adds 31 December.
    assert sorted(d for d in DAYS if d.year == 2000) == [date(2000, 4, 21), date(2000, 4, 24), date(2000, 5, 1),
                                                         date(2000, 12, 25), date(2000, 12, 26)]
    assert date(2001, 12, 31) in DAYS and date(2002, 12, 31) not in DAYS


def test_no_weekend_observance():
    # 2022: New Year on a Saturday, Christmas on a Sunday: no weekday closes for either.
    assert sorted(d for d in DAYS if d.year == 2022) == [date(2022, 4, 15), date(2022, 4, 18), date(2022, 12, 26)]
    assert sorted(d for d in DAYS if d.year == 2026) == [date(2026, 1, 1), date(2026, 4, 3), date(2026, 4, 6),
                                                         date(2026, 5, 1), date(2026, 12, 25)]
