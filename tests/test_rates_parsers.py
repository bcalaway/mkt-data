"""The CMT parsers against real captures (tests/fixtures, exported from the hub with capture-export)."""

from datetime import date
from decimal import Decimal

import pytest

from app.calendars.parsed import ParseError
from app.rates.parsers import parse_h15_tcm, parse_ust_par
from tests.conftest import FIXTURES

UST_SEP = FIXTURES / "ust_par_2026_09_capture31.xml"
UST_OCT = FIXTURES / "ust_par_2026_10_capture32.xml"
H15_SEP = FIXTURES / "h15_tcm_2026_09_capture30.csv"
H15_OCT = FIXTURES / "h15_tcm_2026_10_capture34.csv"


def _by(obs):
    return {(o.source_key, o.as_of): o.value for o in obs}


def test_ust_par_september_2026():
    obs = parse_ust_par(UST_SEP.read_bytes())
    days = sorted({o.as_of for o in obs})
    assert len(days) == 21 and date(2026, 9, 7) not in days  # Labor Day
    keys = {o.source_key for o in obs}
    assert keys == {
        "BC_1MONTH", "BC_1_5MONTH", "BC_2MONTH", "BC_3MONTH", "BC_4MONTH", "BC_6MONTH", "BC_1YEAR", "BC_2YEAR",
        "BC_3YEAR", "BC_5YEAR", "BC_7YEAR", "BC_10YEAR", "BC_20YEAR", "BC_30YEAR",
    }  # no BC_30YEARDISPLAY
    assert len(obs) == 21 * 14
    assert all(o.field == "yield" and o.unit == "percent" for o in obs)


def test_ust_par_values_are_as_printed():
    v = _by(parse_ust_par(UST_OCT.read_bytes()))
    assert v[("BC_1MONTH", date(2026, 10, 1))] == Decimal("4.06")
    assert v[("BC_1_5MONTH", date(2026, 10, 1))] == Decimal("4.10")
    assert str(v[("BC_1_5MONTH", date(2026, 10, 1))]) == "4.10"  # the printed digits, trailing zero kept
    assert v[("BC_10YEAR", date(2026, 10, 1))] == Decimal("5.24")
    assert v[("BC_30YEAR", date(2026, 10, 1))] == Decimal("5.61")


def test_ust_par_and_h15_agree():
    """The same Treasury numbers, two publishers: every H.15 value matches UST-PAR's."""
    ust = _by(parse_ust_par(UST_SEP.read_bytes()))
    h15 = _by(parse_h15_tcm(H15_SEP.read_bytes()))
    pairs = {"RIFLGFCM01_N.B": "BC_1MONTH", "RIFLGFCM03_N.B": "BC_3MONTH", "RIFLGFCM06_N.B": "BC_6MONTH",
             "RIFLGFCY01_N.B": "BC_1YEAR", "RIFLGFCY02_N.B": "BC_2YEAR", "RIFLGFCY03_N.B": "BC_3YEAR",
             "RIFLGFCY05_N.B": "BC_5YEAR", "RIFLGFCY07_N.B": "BC_7YEAR", "RIFLGFCY10_N.B": "BC_10YEAR",
             "RIFLGFCY20_N.B": "BC_20YEAR", "RIFLGFCY30_N.B": "BC_30YEAR"}
    assert len(h15) == 21 * 11
    for (key, day), value in h15.items():
        assert ust[(pairs[key], day)] == value, (key, day)


def test_h15_skips_holidays_and_reads_one_day_months():
    obs = parse_h15_tcm(H15_SEP.read_bytes())
    assert date(2026, 9, 7) not in {o.as_of for o in obs}  # the ND row
    oct_ = parse_h15_tcm(H15_OCT.read_bytes())
    assert {o.as_of for o in oct_} == {date(2026, 10, 1)} and len(oct_) == 11
    assert _by(oct_)[("RIFLGFCY10_N.B", date(2026, 10, 1))] == Decimal("5.24")


def test_an_empty_month_parses_to_nothing():
    feed = UST_OCT.read_bytes()
    empty = feed[: feed.index(b"<entry>")] + b"</feed>"
    assert parse_ust_par(empty) == []
    csv = H15_OCT.read_bytes()
    header_only = csv[: csv.index(b"2026-10-01")]
    assert parse_h15_tcm(header_only) == []


@pytest.mark.parametrize("body", [b"", b"<html>maintenance</html>", b"not xml at all"])
def test_ust_par_rejects_other_pages(body):
    with pytest.raises(ParseError):
        parse_ust_par(body)


def test_h15_rejects_other_pages():
    with pytest.raises(ParseError):
        parse_h15_tcm(b"<html>maintenance</html>")
    bad = H15_SEP.read_bytes().replace(b"RIFLGFCY10_N.B", b"SOMETHING_ELSE", 1)
    with pytest.raises(ParseError):
        parse_h15_tcm(bad.replace(b'"Time Period","RIFLGFCM01_N.B"', b'"Time Period","SOMETHING"'))
    with pytest.raises(ParseError):
        parse_h15_tcm(H15_SEP.read_bytes().replace(b"2026-09-01,3.85", b"2026-09-01,x.85"))


def test_a_new_treasury_tenor_needs_no_parser_change():
    feed = UST_OCT.read_bytes().replace(
        b'<d:BC_1MONTH m:type="Edm.Double">4.06</d:BC_1MONTH>',
        b'<d:BC_1MONTH m:type="Edm.Double">4.06</d:BC_1MONTH><d:BC_5MONTH m:type="Edm.Double">4.30</d:BC_5MONTH>',
        1,
    )
    assert _by(parse_ust_par(feed))[("BC_5MONTH", date(2026, 10, 1))] == Decimal("4.30")
