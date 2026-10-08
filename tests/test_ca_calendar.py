"""Calendar CA: Canada's payments holidays (app/calendars/rules/ca.json), against banks' published lists."""

from datetime import date

from app.calendars import rules

SPEC = rules.parse(rules.read("repo:ca.json"))
DAYS = {d.day: d.holiday for d in SPEC.days}


def _year(y: int) -> list[date]:
    return sorted(d for d in DAYS if d.year == y)


def test_years():
    assert SPEC.years == tuple(range(1990, 2101))


def test_2026_is_pncs_list():
    # PNC's 2026 Canada holiday processing calendar, "No Processing" for AFT and wire.
    assert _year(2026) == [date(2026, 1, 1), date(2026, 4, 3), date(2026, 5, 18), date(2026, 7, 1), date(2026, 9, 7),
                           date(2026, 9, 30), date(2026, 10, 12), date(2026, 11, 11), date(2026, 12, 25),
                           date(2026, 12, 28)]


def test_2025_is_rbcs_list():
    assert _year(2025) == [date(2025, 1, 1), date(2025, 4, 18), date(2025, 5, 19), date(2025, 7, 1), date(2025, 9, 1),
                           date(2025, 9, 30), date(2025, 10, 13), date(2025, 11, 11), date(2025, 12, 25),
                           date(2025, 12, 26)]


def test_2023_is_bmos_list_weekend_holidays_move_to_monday():
    # BMO's 2023 cross-border schedule: New Year's, Canada Day, Truth and Reconciliation and Remembrance Day "in lieu".
    assert _year(2023) == [date(2023, 1, 2), date(2023, 4, 7), date(2023, 5, 22), date(2023, 7, 3), date(2023, 9, 4),
                           date(2023, 10, 2), date(2023, 10, 9), date(2023, 11, 13), date(2023, 12, 25),
                           date(2023, 12, 26)]


def test_christmas_and_boxing_day_on_a_weekend_take_the_next_free_weekdays():
    assert {date(2021, 12, 27), date(2021, 12, 28)} <= set(DAYS)  # Saturday and Sunday
    assert {date(2022, 12, 26), date(2022, 12, 27)} <= set(DAYS)  # Sunday and Monday


def test_what_stays_open():
    assert date(2020, 9, 30) not in DAYS  # Truth and Reconciliation closes from 2021
    assert date(2022, 9, 19) not in DAYS  # the day of mourning for Queen Elizabeth II: Payments Canada open
    assert date(2026, 4, 6) not in DAYS  # Easter Monday
    assert date(2026, 2, 16) not in DAYS and date(2026, 8, 3) not in DAYS  # Family Day, the Civic Holiday: regional
    assert date(2026, 6, 24) not in DAYS  # Saint-Jean-Baptiste: Quebec only


def test_victoria_day_is_the_monday_before_may_25():
    assert DAYS[date(2027, 5, 24)] == "Victoria Day" and DAYS[date(2032, 5, 24)] == "Victoria Day"
    assert DAYS[date(2026, 5, 18)] == "Victoria Day"
