"""The emerging-market calendars' projections past their published years (docs/phase-4.md, step 2d)."""

from datetime import date

import pytest

from app.calendars import rules, service

FIRST = {"cl": 2027, "in": 2027, "cn": 2027, "hk": 2028, "kr": 2028, "il": 2028, "tr": 2028, "sg": 2028, "th": 2028,
         "id": 2028}


def _days(name: str) -> dict:
    return {d.day: d for d in rules.parse(rules.read(f"repo:{name}.json")).days}


@pytest.mark.projections
@pytest.mark.parametrize("name", FIRST)
def test_each_projection_starts_after_its_published_years_and_runs_to_2035(name):
    published = rules.parse(rules.read(f"repo:{name}.json")).years
    projected = rules.parse(rules.read(f"repo:{name}_projected.json")).years
    assert projected == tuple(range(published[-1] + 1, 2036)) and projected[0] == FIRST[name]
    assert service.SOURCES[f"{name.upper()}-PROJECTED"].projected


def test_lunar_holidays_are_projected():
    kr, cn, hk = _days("kr_projected"), _days("cn_projected"), _days("hk_projected")
    assert {date(2028, 1, 26), date(2028, 1, 27), date(2028, 1, 28)} <= set(kr)  # Seollal 2028
    assert date(2027, 2, 8) in cn and date(2027, 10, 1) in cn  # Spring Festival, National Day
    assert date(2028, 1, 26) in hk  # the second day of Lunar New Year 2028


def test_turkeys_eves_stay_half_days():
    tr = _days("tr_projected")
    assert tr[date(2030, 10, 28)].status == "early_close"  # Republic Day eve, a Monday
