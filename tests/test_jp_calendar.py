"""Calendar JP: the Cabinet Office's holidays CSV (app/calendars/jpcao.py), bank holidays and the projection."""

import json
from datetime import date

import pytest

from app.calendars import jpcao, rules
from app.calendars.parsed import ParseError
from tests.conftest import FIXTURES

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


def test_names_are_english_and_a_holiday_is_named_from_its_neighbours():
    names = {d.day: d.holiday for d in jpcao.parse(_csv(ROWS_2026)).days}
    assert names[date(2026, 1, 1)] == "New Year's Day" and names[date(2026, 10, 12)] == "Sports Day"
    assert names[date(2026, 5, 6)] == "Constitution Memorial Day (observed)"  # May 3, a Sunday
    assert names[date(2026, 9, 22)] == "Citizens' Holiday"  # between Respect for the Aged Day and the equinox


@pytest.mark.parametrize(("rows", "message"), [
    (ROWS_2026[:5], "fewer than 9"),
    ([*ROWS_2026, ("2026/1/1", "元日")], "listed twice"),
    ([*ROWS_2026, ("2026-13-1", "x")], "can't read"),
    ([*ROWS_2026, ("2026/6/1", "新しい祝日")], "no English name"),
    ([*ROWS_2026, ("2026/6/2", "休日")], "neither a substitute"),
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


CAO = (FIXTURES / "jp_cao_holidays_capture8323.csv").read_bytes()  # the hub's first capture, 2026-10-08


def test_the_real_csv_and_the_projection_agree_but_for_the_olympics():
    p = jpcao.parse(CAO)
    assert p.years == tuple(range(1955, 2028)) and len(p.days) == 821
    names = {d.day: d.holiday for d in p.days}
    assert names[date(1989, 2, 24)] == "State Funeral of Emperor Showa"
    assert names[date(2019, 5, 1)] == "Accession of the Emperor" and names[date(2019, 5, 2)] == "Citizens' Holiday"
    assert names[date(1989, 1, 2)] == "New Year's Day (observed)"
    published = {d.day for d in p.days if d.day.year >= 2020}
    spec = json.loads(rules.read("repo:jp_projected.json")) | {"first_year": 2020, "last_year": 2027}
    projected = {d.day for d in rules.parse(json.dumps(spec).encode()).days}
    # The Tokyo Olympics moved Marine Day, Sports Day and Mountain Day in 2020 and 2021 (special acts); every other
    # day of 2020-2027 is exactly what the current law gives.
    olympics = {date(2020, 7, 23), date(2020, 7, 24), date(2020, 8, 10), date(2021, 7, 22), date(2021, 7, 23),
                date(2021, 8, 9)}
    assert published - projected == olympics
    # Named alike: every day of 2022-2027 has the projection's name.
    names = {d.day: d.holiday for d in p.days if d.day.year >= 2022}
    spec |= {"first_year": 2022}
    assert names == {d.day: d.holiday for d in rules.parse(json.dumps(spec).encode()).days}
    assert projected - published == {date(2020, 7, 20), date(2020, 8, 11), date(2020, 10, 12), date(2021, 7, 19),
                                      date(2021, 8, 11), date(2021, 10, 11)}
