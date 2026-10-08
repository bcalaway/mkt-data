"""CME's business-day calendars (app/calendars/rules/cme_*.json; docs/phase-4.md, "Calendars")."""

from datetime import date, timedelta

import pytest

from app.calendars import rules, service


def _closed(name: str) -> set[date]:
    days = set()
    for f in (f"{name}.json", f"{name}_projected.json"):
        days |= {d.day for d in rules.parse(rules.read(f"repo:{f}")).days if d.status == "closed"}
    return days


IR, FX = _closed("cme_ir"), _closed("cme_fx")


def _business(d: date, closed: set[date]) -> bool:
    return d.weekday() < 5 and d not in closed


def _before(d: date, n: int, closed: set[date]) -> date:
    """The n-th business day before d."""
    while n:
        d -= timedelta(days=1)
        n -= _business(d, closed)
    return d


def test_years_and_registration():
    for name in ("cme_ir", "cme_fx"):
        assert rules.parse(rules.read(f"repo:{name}.json")).years == tuple(range(1990, 2027))
        assert rules.parse(rules.read(f"repo:{name}_projected.json")).years == tuple(range(2027, 2101))
    # (tests/conftest.py leaves the projections out of the registered sources)
    assert service.CALENDARS["CME-IR"].source_names[0] == "CME-IR-RULES"
    assert service.CALENDARS["CME-FX"].source_names[0] == "CME-FX-RULES"


@pytest.mark.parametrize(("day", "ir", "fx"), [
    (date(2026, 4, 3), True, True),  # Good Friday with payrolls: traded and settled (2026 clearing advisory)
    (date(2025, 4, 18), False, False),  # an ordinary Good Friday
    (date(2023, 4, 7), True, True), (date(2021, 4, 2), True, True), (date(2015, 4, 3), True, True),
    (date(2012, 4, 6), True, True), (date(2010, 4, 2), True, True), (date(2007, 4, 6), True, True),
    (date(2018, 12, 5), False, True),  # Bush mourning day: interest rates closed, FX open
    (date(2025, 1, 9), True, True),  # Carter: rates closed early at 12:15 CT, still a business day
    (date(2012, 10, 29), False, True), (date(2012, 10, 30), True, True),  # Sandy
    (date(2001, 9, 11), False, False), (date(2001, 9, 12), False, False), (date(2001, 9, 13), True, True),
    (date(2001, 9, 14), True, True),
    (date(2004, 6, 11), True, True),  # Reagan: CBOT financials closed early, a business day
    (date(1994, 4, 27), True, True),  # Nixon: CBOT held a regular session
    (date(2007, 1, 2), True, True),  # Ford: open until noon CT
    (date(2026, 10, 12), True, True), (date(2026, 11, 11), True, True),  # Columbus and Veterans Day: CME open
    (date(2022, 6, 20), False, False),  # Juneteenth (Sunday) observed Monday, from 2022
    (date(2021, 6, 18), True, True),  # not yet a CME holiday in 2021
    (date(2027, 1, 18), False, False), (date(2027, 3, 26), False, False),  # projected MLK Day, Good Friday
])
def test_business_days(day, ir, fx):
    assert _business(day, IR) is ir and _business(day, FX) is fx


def test_juneteenth_moves_fx_last_trading_days_as_cme_did():
    # SER-8887: the June 2023 EUR/USD, GBP/USD, JPY/USD, AUD/USD and CHF/USD futures' last trading day moved to
    # 2023-06-16, the second business day before the third Wednesday (June 21) with Monday June 19 closed.
    assert _before(date(2023, 6, 21), 2, FX) == date(2023, 6, 16)
