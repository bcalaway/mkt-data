"""Parsers for the Treasury securities sources (phase 3, step 2), on real captures from the hub."""

import json
from collections import Counter
from datetime import date
from decimal import Decimal

import pytest

from app.calendars.parsed import ParseError
from app.securities import parsers as p
from tests.conftest import FIXTURES


def _read(name: str) -> bytes:
    return (FIXTURES / name).read_bytes()


TD_OCT = _read("td_securities_2026_10_capture1261.json")
TD_1980 = _read("td_securities_1980_02_capture1273.json")
FD_OCT = _read("fd_auctions_2026_10_capture1263.json")
MSPD_SEP = _read("fd_mspd_strips_2026_09_capture1264.json")
PRICES_OCT5 = _read("td_prices_2026_10_05_capture1270.html")
PRICES_OCT6 = _read("td_prices_2026_10_06_capture1271.html")
PRICES_2009 = _read("td_prices_2009_01_14_capture1419.html")
PRICES_2008 = _read("td_prices_2008_01_09_capture1418.html")
BLS_2026 = _read("bls_cpi_2026_capture1267.json")


def test_td_securities():
    recs = p.parse_td_securities(TD_OCT)
    assert len(recs) == 11 and {r.record_type for r in recs} == {"auction"}
    bond = next(r for r in recs if r.source_key == "912810UW6/2026-10-15")
    assert bond.as_of == date(2026, 10, 8)
    # Kept exactly as published: TreasuryDirect's own names, strings, "" for blanks.
    f = bond.fields
    assert f["interestRate"] == "5.125000" and f["datedDate"] == "2026-08-15T00:00:00"
    assert f["firstInterestPaymentDate"] == "2027-02-15T00:00:00" and f["corpusCusip"] == "912803HX4"
    assert f["reopening"] == "Yes" and f["originalSecurityTerm"] == "30-Year" and f["highYield"] == ""
    assert all(date(2026, 10, 1) <= r.as_of <= date(2026, 10, 31) for r in recs)
    # An interest STRIPS CUSIP turns up on one of them.
    assert any(r.fields.get("tintCusip1") == "912834L89" for r in recs)


def test_td_securities_1980():
    recs = p.parse_td_securities(TD_1980)
    assert len(recs) == 14
    assert Counter(r.fields["securityType"] for r in recs) == {"Bill": 9, "Note": 4, "Bond": 1}
    assert all(r.as_of.year == 1980 and r.as_of.month == 2 for r in recs)


def test_td_securities_errors():
    assert p.parse_td_securities(b"[]") == []
    for bad in (b"{}", b"<html>", b'[{"issueDate": "2026-10-15"}]', b'[{"cusip": "X", "issueDate": "soon"}]'):
        with pytest.raises(ParseError):
            p.parse_td_securities(bad)
    one = {"cusip": "X", "issueDate": "2026-10-15T00:00:00", "auctionDate": "2026-10-08T00:00:00"}
    assert len(p.parse_td_securities(json.dumps([one, one]).encode())) == 1  # an exact repeat is dropped
    with pytest.raises(ParseError, match="two different records"):
        p.parse_td_securities(json.dumps([one, one | {"interestRate": "4"}]).encode())


def test_fd_auctions_match_treasurydirect():
    fd = {r.source_key: r for r in p.parse_fd_auctions(FD_OCT)}
    td = {r.source_key: r for r in p.parse_td_securities(TD_OCT)}
    assert len(fd) == 11 and set(fd) == set(td)  # the same auctions, keyed the same way
    k = "912797VP9/2026-10-06"
    assert fd[k].fields["high_discnt_rate"] == "3.890000" and fd[k].fields["corpus_cusip"] == "null"


def test_fiscal_data_paging_is_checked():
    doc = json.loads(FD_OCT)
    doc["meta"]["total-pages"] = 2
    with pytest.raises(ParseError, match="2 pages"):
        p.parse_fd_auctions(json.dumps(doc).encode())


def test_mspd_strips():
    recs = p.parse_fd_mspd_strips(MSPD_SEP)
    assert Counter(r.record_type for r in recs) == {"stripped_security": 406, "stripped_total": 4}
    first = next(r for r in recs if r.source_key == "912821NH4/2026-09-30")
    assert first.fields["security_class2_desc"] == "91282CJC6" and first.fields["portion_stripped_amt"] == "100200"
    totals = {r.source_key.split("/")[0] for r in recs if r.record_type == "stripped_total"}
    assert "Grand Total" in totals and "Total Treasury Notes" in totals
    # The per-security lines add up to the grand total's stripped amount.
    lines = sum(Decimal(r.fields["portion_stripped_amt"]) for r in recs if r.record_type == "stripped_security")
    grand = next(r for r in recs if r.source_key.startswith("Grand Total/"))
    assert abs(lines - Decimal(grand.fields["portion_stripped_amt"])) < 1


def test_prices():
    obs = p.parse_td_prices(PRICES_OCT5)
    by = {(o.source_key, o.field): o.value for o in obs}
    assert len({o.source_key for o in obs}) == 464 and {o.as_of for o in obs} == {date(2026, 10, 5)}
    assert {o.unit for o in obs} == {"per_100"}
    assert by[("912810UW6", "buy")] == Decimal("92.078125") and by[("912810UW6", "eod")] == Decimal("92.250000")
    # 0.000000 is "not available", not a price: a bill maturing tomorrow has no buy price.
    assert ("912797VK0", "buy") not in by and by[("912797VK0", "eod")] == Decimal("100.000000")


def test_prices_before_end_of_day():
    obs = p.parse_td_prices(PRICES_OCT6)
    assert Counter(o.field for o in obs) == {"sell": 464, "buy": 432}  # end of day comes the next day


def test_prices_2009_and_an_empty_day():
    assert len({o.source_key for o in p.parse_td_prices(PRICES_2009)}) == 235
    assert p.parse_td_prices(PRICES_2008) == []  # before FedInvest's history: the header row only


def test_prices_errors():
    for bad in (b"<html><body>Login</body></html>", PRICES_OCT5.replace(b"Prices For:", b"Prices:"),
                PRICES_OCT5.replace(b"<th>BUY</th>", b"<th>BID</th>"),
                PRICES_OCT5.replace(b"<td>92.078125</td>", b"<td>n/a</td>", 1)):
        with pytest.raises(ParseError):
            p.parse_td_prices(bad)


def test_bls_cpi():
    obs = p.parse_bls_cpi(BLS_2026)
    assert len(obs) == 8 and {o.source_key for o in obs} == {"CUUR0000SA0"}
    by = {o.as_of: o.value for o in obs}
    assert by[date(2026, 8, 1)] == Decimal("334.980") and min(by) == date(2026, 1, 1)


def test_bls_cpi_gaps_and_errors():
    doc = json.loads(BLS_2026)
    rows = doc["Results"]["series"][0]["data"]
    rows.append({"year": "2026", "period": "M13", "value": "330.0"})  # annual average: left out
    rows[0] = rows[0] | {"value": "-"}  # never published (October 2025's shutdown): no value
    assert len(p.parse_bls_cpi(json.dumps(doc).encode())) == 7
    with pytest.raises(ParseError, match="not processed"):
        p.parse_bls_cpi(json.dumps({"status": "REQUEST_NOT_PROCESSED", "message": ["daily threshold"]}).encode())
