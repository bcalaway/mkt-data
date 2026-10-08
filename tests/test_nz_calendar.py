"""Calendar NZ: New Zealand's NZD settlement holidays (app/calendars/rules/nz.json), against ANZ's list."""

from datetime import date

from app.calendars import rules

SPEC = rules.parse(rules.read("repo:nz.json"))
DAYS = {d.day: d.holiday for d in SPEC.days}


def _year(y: int) -> list[date]:
    return sorted(d for d in DAYS if d.year == y)


def test_years():
    assert SPEC.years == tuple(range(1990, 2101))


def test_anz_2023_to_2025():
    # ANZ's New Zealand public holidays 2023-2025: the days banks, NZClear and ESAS close. (ANZ prints 2024's King's
    # Birthday as "Monday 6 June", a Thursday; the first Monday in June 2024 is the 3rd.)
    assert _year(2023) == [date(2023, 1, 2), date(2023, 1, 3), date(2023, 2, 6), date(2023, 4, 7), date(2023, 4, 10),
                           date(2023, 4, 25), date(2023, 6, 5), date(2023, 7, 14), date(2023, 10, 23),
                           date(2023, 12, 25), date(2023, 12, 26)]
    assert _year(2024) == [date(2024, 1, 1), date(2024, 1, 2), date(2024, 2, 6), date(2024, 3, 29), date(2024, 4, 1),
                           date(2024, 4, 25), date(2024, 6, 3), date(2024, 6, 28), date(2024, 10, 28),
                           date(2024, 12, 25), date(2024, 12, 26)]
    assert _year(2025) == [date(2025, 1, 1), date(2025, 1, 2), date(2025, 2, 6), date(2025, 4, 18), date(2025, 4, 21),
                           date(2025, 4, 25), date(2025, 6, 2), date(2025, 6, 20), date(2025, 10, 27),
                           date(2025, 12, 25), date(2025, 12, 26)]


def test_anniversary_days_are_settlement_days():
    assert date(2026, 1, 19) not in DAYS and date(2026, 1, 26) not in DAYS  # Wellington, Auckland


def test_mondayisation_of_waitangi_and_anzac_from_2014():
    assert date(2010, 2, 8) not in DAYS  # Waitangi Day 2010 a Saturday: no weekday
    assert DAYS[date(2015, 4, 27)] == "Anzac Day (observed)" and DAYS[date(2016, 2, 8)] == "Waitangi Day (observed)"


def test_matariki_from_the_acts_schedule():
    assert DAYS[date(2022, 6, 24)] == "Matariki" and DAYS[date(2052, 6, 21)] == "Matariki"
    assert date(2021, 7, 2) not in DAYS and not [d for d, n in DAYS.items() if n == "Matariki" and d.year > 2052]


def test_one_offs():
    assert DAYS[date(2022, 9, 26)] == "Queen Elizabeth II Memorial Day"
    assert DAYS[date(2011, 4, 25)] == "Easter Monday and Anzac Day" and date(2011, 4, 26) not in DAYS
