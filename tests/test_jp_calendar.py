"""Calendar JP: the Cabinet Office's holidays CSV (app/calendars/jpcao.py), bank holidays and the projection."""

from datetime import date

import pytest

from app.calendars import jpcao, rules
from app.calendars.parsed import ParseError

ROWS_2026 = [  # the Cabinet Office's 2026, as the law gives it (the real file's rows look like this)
    ("2026/1/1", "元日"), ("2026/1/12", "成人の日"), ("2026/2/11", "建国記念の日"), ("2026/2/23", "天皇誕生日"),
    ("2026/3/20", "春分の日"), ("2026/4/29", "昭和の日"), ("2026/5/3", "憲法記念日"), ("2026/5/4", "みどりの日"),
    ("2026/5/5", "こどもの日"), ("2026/5/6", "休日"), ("2026/7/20", "海の日"), ("2026/8/11", "山の日"),
    ("2026/9/21", "敬老の日"), ("2026/9/22", "休日"), ("2026/9/23", "秋分の日"), ("2026/10/12", "スポーツの日"),
    ("2026/11/3", "文化の日"), ("2026/11/23", "勤労感謝の日"),
]


def _csv(rows) -> bytes:
    text = "国民の祝日・休日月日,国民の祝日・休日名称\r\n" + "".join(f"{d},{n}\r\n" for d, n in rows)
    return text.encode("cp932")


def test_parse_reads_shift_jis_and_drops_weekends():
    p = jpcao.parse(_csv(ROWS_2026))
    assert p.years == (2026,)
    days = {d.day for d in p.days}
    assert date(2026, 5, 3) not in days  # a Sunday: closes nothing (its substitute, May 6, is listed)
    assert date(2026, 5, 6) in days and date(2026, 9, 22) in days and len(days) == 17


@pytest.mark.parametrize(("rows", "message"), [
    (ROWS_2026[:5], "fewer than 10"),
    ([*ROWS_2026, ("2026/1/1", "元日")], "listed twice"),
    ([*ROWS_2026, ("2026-13-1", "x")], "can't read"),
])
def test_parse_refuses_what_it_doesnt_understand(rows, message):
    with pytest.raises(ParseError, match=message):
        jpcao.parse(_csv(rows))


def test_projection_reproduces_2026():
    proj = rules.parse(rules.read("repo:jp_projected.json"))
    assert {d.day for d in proj.days if d.day.year == 2026} == {d.day for d in jpcao.parse(_csv(ROWS_2026)).days}


def test_projection_rules():
    days = {d.day: d.holiday for d in rules.parse(rules.read("repo:jp_projected.json")).days}
    assert days[date(2032, 9, 21)] == "Citizens' Holiday"  # between Respect for the Aged (20th) and the equinox
    assert days[date(2037, 5, 6)] == "Constitution Memorial Day (observed)"  # May 3 a Sunday: past May 4 and 5
    assert date(2100, 12, 31) not in days  # a bank holiday, not a national one (jp_bank.json)


def test_bank_holidays_add_dates_without_covering_years():
    p = rules.parse(rules.read("repo:jp_bank.json"))
    days = {d.day for d in p.days}
    assert p.years == () and {date(2025, 12, 31), date(2026, 1, 2)} <= days and date(2026, 1, 3) not in days
