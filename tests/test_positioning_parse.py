"""Phase 4, step 5: the CFTC's Traders in Financial Futures parser (app/futures/parsers.py).

The fixture is three markets of the combined report of 2018-06-19 (capture #8240 on the hub, exported
2026-10-10): 10-year T-notes, the Swiss franc (some trader counts withheld) and the Dow's consolidated
market (a code ending in +).
"""

from datetime import date
from decimal import Decimal

import pytest
from sqlalchemy import select

from app import db
from app.calendars import service
from app.calendars.parsed import ParseError
from app.futures import parsers as p
from app.futures import sources as fut
from app.models import Observation
from tests.conftest import FIXTURES

HEAD = b"id,report_date_as_yyyy_mm_dd,cftc_contract_market_code,open_interest_all\n"
BODY = (FIXTURES / "cftc_tff_combined_2018_06_19.csv").read_bytes()
DAY = date(2018, 6, 19)


def _by(obs):
    return {(o.source_key, o.field): o for o in obs}


def test_the_published_levels_as_printed():
    got = _by(p.parse_tff_combined(BODY))
    ty = {f: o for (k, f), o in got.items() if k == "043602"}
    assert ty["open_interest_all"].value == Decimal(4349750) and ty["open_interest_all"].unit == "contracts"
    assert ty["lev_money_positions_short"].value == Decimal(921596)
    assert ty["dealer_positions_spread_all"].value == Decimal(220485)
    assert ty["traders_tot_all"].value == Decimal(472) and ty["traders_tot_all"].unit == "traders"
    assert ty["conc_net_le_8_tdr_short_all"].value == Decimal("14.1") and ty["conc_net_le_8_tdr_short_all"].unit == "percent"
    assert {o.as_of for o in got.values()} == {DAY}
    # 1 + 16 positions + 15 trader counts + 8 concentration ratios; not the changes or percents of open interest.
    assert len(ty) == 40
    assert not [f for f in ty if f.startswith(("change_in_", "pct_of_"))]


def test_withheld_counts_are_skipped_and_codes_kept_as_printed():
    got = _by(p.parse_tff_combined(BODY))
    chf = {f for (k, f) in got if k == "092741"}
    assert "open_interest_all" in chf and "traders_asset_mgr_spread" not in chf
    assert ("12460+", "open_interest_all") in got


def test_the_wrong_report_is_refused():
    with pytest.raises(ParseError, match="futures-only"):
        p.parse_tff(BODY)


@pytest.mark.parametrize(("body", "match"), [
    (b"id,report_date_as_yyyy_mm_dd\n", "missing columns"),
    (HEAD + b"x1C,2018-06-19T00:00:00.000,043602,1\nx2C,2018-06-19T00:00:00.000,043602,2\n", "twice"),
    (HEAD + b"x1C,2018-06-19T00:00:00.000,043602,1\nx2C,2018-06-26T00:00:00.000,044601,2\n", "more than one report date"),
    (HEAD + b"x1C,2018-06-19T00:00:00.000,043602,n/a\n", "isn't a number"),
])
def test_bad_reports(body, match):
    with pytest.raises(ParseError, match=match):
        p.parse_tff_combined(body)


def test_a_capture_stores_the_observations(migrated_db, monkeypatch):
    monkeypatch.setattr(service, "fetch", lambda url: (200, "text/csv", BODY))
    with db.session() as s:
        r = fut.run_capture(s, "CFTC-TFF-COMBINED", "2018-06-19")
        assert r["parsed"] and r["values"] == len(p.parse_tff_combined(BODY))
    with db.session() as s:
        row = s.scalars(select(Observation).where(Observation.source_key == "043602",
                                                  Observation.field == "dealer_positions_spread_all")).one()
        assert (row.period, row.as_of, row.value) == ("2018-06-19", DAY, Decimal(220485))
