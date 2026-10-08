"""Calendars SE, NO, DK and MX (app/calendars/rules/se.json, no.json, dk.json, mx.json), against published lists."""

from datetime import date

import pytest

from app.calendars import nbo, rules, service
from app.calendars.parsed import ParseError
from tests.conftest import FIXTURES


def _days(name: str) -> dict[date, str]:
    return {d.day: d.holiday for d in rules.parse(rules.read(f"repo:{name}.json")).days}


SE, NO, DK, MX = _days("se"), _days("no"), _days("dk"), _days("mx")


def _year(days: dict, y: int) -> list[str]:
    return [f"{d:%m-%d}" for d in sorted(days) if d.year == y]


@pytest.mark.parametrize("name", ["se", "no", "dk", "mx"])
def test_years(name):
    assert rules.parse(rules.read(f"repo:{name}.json")).years == tuple(range(1990, 2101))


def test_registered():
    assert service.CALENDARS["NO"].source_names == ["NO-NBO", "NO-RULES"]


def test_se_is_sebs_lists():
    assert _year(SE, 2024) == ["01-01", "03-29", "04-01", "05-01", "05-09", "06-06", "06-21", "12-24", "12-25", "12-26",
                               "12-31"]
    assert _year(SE, 2026) == ["01-01", "01-06", "04-03", "04-06", "05-01", "05-14", "06-19", "12-24", "12-25", "12-31"]


def test_se_national_day_replaced_whit_monday_in_2005():
    assert SE[date(2004, 5, 31)] == "Whit Monday" and date(2005, 5, 16) not in SE
    assert date(2004, 6, 7) not in SE and SE[date(2005, 6, 6)] == "National Day"
    assert SE[date(2008, 5, 1)] == "Labour Day and Ascension Day"


def test_no_is_norges_banks_and_sebs_lists():
    assert _year(NO, 2024) == ["01-01", "03-28", "03-29", "04-01", "05-01", "05-09", "05-17", "05-20", "12-24", "12-25",
                               "12-26"]
    # Norges Bank's 2026 list (Constitution Day and Boxing Day fall on a Sunday and a Saturday).
    assert _year(NO, 2026) == ["01-01", "04-02", "04-03", "04-06", "05-01", "05-14", "05-25", "12-24", "12-25"]
    assert date(2026, 12, 31) not in NO  # New Year's Eve is a settlement day
    assert NO[date(2007, 5, 17)] == "Ascension Day and Constitution Day"


def test_dk_is_sebs_lists():
    assert _year(DK, 2024) == ["01-01", "03-28", "03-29", "04-01", "05-09", "05-10", "05-20", "06-05", "12-24", "12-25",
                               "12-26", "12-31"]
    assert _year(DK, 2026) == ["01-01", "04-02", "04-03", "04-06", "05-14", "05-15", "05-25", "06-05", "12-24", "12-25",
                               "12-31"]


def test_dk_great_prayer_day_to_2023():
    assert DK[date(2023, 5, 5)] == "Great Prayer Day" and date(2024, 4, 26) not in DK
    assert date(2026, 5, 1) not in DK  # May 1 isn't a bank holiday


def test_mx_is_the_cnbvs_lists():
    # The CNBV's 2024 closing days (DOF, 2023-12-12), with the October 1 inauguration.
    assert _year(MX, 2024) == ["01-01", "02-05", "03-18", "03-28", "03-29", "05-01", "09-16", "10-01", "11-18", "12-12",
                               "12-25"]
    # 2026 (DOF, 2025-12-10): December 12 is a Saturday.
    assert _year(MX, 2026) == ["01-01", "02-02", "03-16", "04-02", "04-03", "05-01", "09-16", "11-02", "11-16", "12-25"]


def test_mx_mondays_from_2006_and_inaugurations():
    assert MX[date(2005, 3, 21)] == "Benito Juárez's Birthday" and MX[date(2006, 3, 20)] == "Benito Juárez's Birthday"
    assert MX[date(2006, 12, 1)] == "Presidential Inauguration" and MX[date(2030, 10, 1)] == "Presidential Inauguration"
    assert date(2025, 10, 1) not in MX


NBO = (FIXTURES / "no_nbo_settlement_days_capture8332.html").read_bytes()  # the hub's first capture, 2026-10-08


def test_norges_banks_page_matches_the_rules():
    p = nbo.parse(NBO)
    assert p.years == (2026,)
    assert {d.day for d in p.days} == {d for d in NO if d.year == 2026}  # weekend rows (May 17, Dec 26) dropped
    assert {d.day: d.holiday for d in p.days}[date(2026, 4, 2)] == "Maundy Thursday"


PAGE = ("<p>" + nbo.INTRO + "</p><p>2027</p>" + "".join(f"<p>{r}</p>" for r in (
    "1 January: New Year's Day", "25 March: Maundy Thursday", "26 March: Good Friday", "29 March: Easter Monday",
    "1 May: Labour Day (Saturday)", "6 May: Ascension Day", "17 May: Constitution Day", "17 May: Whit Monday",
    "24 December: Christmas Eve", "25 December: Christmas Day (Saturday)", "26 December: Boxing Day (Sunday)",
)) + "<p>Edited 5 November 2026</p>")


def test_nbo_one_day_for_two_holidays_as_the_rules_have_it():
    p = nbo.parse(PAGE.encode())
    assert p.years == (2027,)
    assert {d.day: d.holiday for d in p.days}[date(2027, 5, 17)] == "Constitution Day and Whit Monday"
    assert {d.day for d in p.days} == {d for d in NO if d.year == 2027}
    assert NO[date(2027, 5, 17)] == "Constitution Day and Whit Monday"


@pytest.mark.parametrize(("page", "message"), [
    ("<p>Settlement days</p>", "no line"),
    (PAGE.replace("(Saturday)</p><p>6 May", "(Friday)</p><p>6 May"), "isn't a Friday"),
    (PAGE.replace("29 March", "30 Febtober"), "can't read"),
    (PAGE.split("<p>24 December")[0], "fewer than 10"),
])
def test_nbo_refuses_what_it_doesnt_understand(page, message):
    with pytest.raises(ParseError, match=message):
        nbo.parse(page.encode())
