"""Calendar AU: Sydney's AUD settlement holidays (app/calendars/rules/au.json), against ANZ's and NSW's lists."""

from datetime import date

from app.calendars import rules

SPEC = rules.parse(rules.read("repo:au.json"))
DAYS = {d.day: d.holiday for d in SPEC.days}


def _year(y: int) -> list[date]:
    return sorted(d for d in DAYS if d.year == y)


def test_years():
    assert SPEC.years == tuple(range(1990, 2101))


def test_anz_2024_to_2026():
    # ANZ's Australian public holidays: national, plus NSW's King's Birthday, Bank Holiday and Labour Day.
    assert _year(2024) == [date(2024, 1, 1), date(2024, 1, 26), date(2024, 3, 29), date(2024, 4, 1), date(2024, 4, 25),
                           date(2024, 6, 10), date(2024, 8, 5), date(2024, 10, 7), date(2024, 12, 25),
                           date(2024, 12, 26)]
    assert _year(2025) == [date(2025, 1, 1), date(2025, 1, 27), date(2025, 4, 18), date(2025, 4, 21), date(2025, 4, 25),
                           date(2025, 6, 9), date(2025, 8, 4), date(2025, 10, 6), date(2025, 12, 25),
                           date(2025, 12, 26)]
    assert _year(2026) == [date(2026, 1, 1), date(2026, 1, 26), date(2026, 4, 3), date(2026, 4, 6), date(2026, 4, 27),
                           date(2026, 6, 8), date(2026, 8, 3), date(2026, 10, 5), date(2026, 12, 25),
                           date(2026, 12, 28)]


def test_nsw_2027():
    # NSW's list: Anzac Day on a Sunday with its additional Monday; Christmas and Boxing Day on the weekend.
    assert _year(2027) == [date(2027, 1, 1), date(2027, 1, 26), date(2027, 3, 26), date(2027, 3, 29), date(2027, 4, 26),
                           date(2027, 6, 14), date(2027, 8, 2), date(2027, 10, 4), date(2027, 12, 27),
                           date(2027, 12, 28)]


def test_anzac_day_on_a_weekend_moves_only_by_order():
    assert date(2021, 4, 26) not in DAYS  # Sunday Anzac Day 2021: no additional day
    assert date(2032, 4, 26) not in DAYS  # the 2026 order named 2026 and 2027 only


def test_2011_anzac_day_on_easter_monday():
    assert DAYS[date(2011, 4, 25)] == "Easter Monday and Anzac Day"
    assert date(2011, 4, 26) in DAYS  # the substitute for Easter Monday


def test_one_offs_and_history():
    assert DAYS[date(2022, 9, 22)] == "National Day of Mourning (Queen Elizabeth II)"
    assert DAYS[date(1993, 2, 1)] == "Australia Day" and date(1993, 1, 26) not in DAYS  # the long-weekend Monday
    assert DAYS[date(2022, 6, 13)] == "Queen's Birthday" and DAYS[date(2023, 6, 12)] == "King's Birthday"
