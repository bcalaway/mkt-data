"""Calendars IN and KR (app/calendars/rules/), against published lists (docs/phase-4.md, step 2d)."""

from datetime import date

from app.calendars import rules, service


def _parsed(name: str):
    return rules.parse(rules.read(f"repo:{name}.json"))


def _weekdays(name: str, y: int) -> list[str]:
    return [f"{d.day:%m-%d}" for d in _parsed(name).days if d.day.year == y and d.day.weekday() < 5]


def test_years_and_registration():
    assert _parsed("in").years == tuple(range(2017, 2027))
    assert _parsed("kr").years == tuple(range(2010, 2028))
    for c in ("IN", "KR"):
        assert service.CALENDARS[c].source_names == [f"{c}-RULES"]


def test_in_is_nse_clearings_settlement_holidays():
    # NSE Clearing's 2026 settlement holidays (CD71921) with CCIL's January 15 (municipal elections); April 1 closes.
    assert _weekdays("in", 2026) == [
        "01-15", "01-26", "02-19", "03-03", "03-19", "03-26", "03-31", "04-01", "04-03", "04-14", "05-01", "05-28",
        "06-26", "08-26", "09-14", "10-02", "10-20", "11-10", "11-24", "12-25"]
    # 2025's Id-e-Milad moved from September 5 to 8 in Mumbai (RBI press release).
    days = _weekdays("in", 2025)
    assert "09-08" in days and "09-05" not in days


def test_kr_is_kasis_list_with_designated_days():
    # KASI's 2027 list: Labour Day (from 2026) on a Saturday, substituted May 3; Constitution Day's substitute July 19.
    assert _weekdays("kr", 2027) == [
        "01-01", "02-08", "02-09", "03-01", "05-03", "05-05", "05-13", "07-19", "08-16", "09-14", "09-15", "09-16",
        "10-04", "10-11", "12-27"]
    kr = {d.day for d in _parsed("kr").days}
    assert date(2025, 6, 3) in kr and date(2025, 1, 27) in kr  # the snap election, the temporary holiday
    assert date(2025, 12, 31) not in kr  # banks and BOK-Wire+ run; only KRX and the interbank FX market close
