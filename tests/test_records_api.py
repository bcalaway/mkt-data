"""The Records read API (proto/records.proto, phase 3 step 2): what secmaster-svc pulls."""

import json

import pytest

from app import db
from app.securities import api
from app.securities import sources as sec
from tests.conftest import FIXTURES

TD_OCT = (FIXTURES / "td_securities_2026_10_capture1261.json").read_bytes()
MSPD_SEP = (FIXTURES / "fd_mspd_strips_2026_09_capture1264.json").read_bytes()


def _capture(name: str, period: str, body: bytes):
    with db.session() as s:
        sec.run_capture(s, name, period, lambda url: (200, "application/json", body))


def test_sources_are_listed_before_anything_is_captured(migrated_db):
    with db.session() as s:
        listed = {r["name"]: r for r in api.list_sources(s)}
        assert api.list_periods(s, "TD-SECURITIES") == [] and api.get_period(s, "TD-SECURITIES", "2026-10") == []
    assert set(listed) == {"TD-SECURITIES", "FD-AUCTIONS", "FD-MSPD-STRIPS"} | {f"SPGMI-RFR-{c}" for c in ("USD", "EUR", "GBP", "JPY", "CHF", "AUD")}  # curve records
    assert listed["TD-SECURITIES"]["calendar"] == "SIFMA-US" and listed["TD-SECURITIES"]["periods"] == 0


def test_periods_and_a_revision_moving_the_watermark(migrated_db):
    _capture("TD-SECURITIES", "2026-10", TD_OCT)
    _capture("TD-SECURITIES", "2026-09", b"[]")
    with db.session() as s:
        periods = api.list_periods(s, "TD-SECURITIES")
        assert [(p["period"], p["records"]) for p in periods] == [("2026-10", 11)]  # an empty month has no rows
        assert periods[0]["first_date"] == "2026-10-01" and periods[0]["last_date"] == "2026-10-08"
        before = periods[0]["latest_capture_id"]
    doc = json.loads(TD_OCT)
    doc[1] = doc[1] | {"highDiscountRate": "3.880000"}
    _capture("TD-SECURITIES", "2026-10", json.dumps(doc).encode())
    with db.session() as s:
        after = api.list_periods(s, "TD-SECURITIES", since_period="2026-10")[0]
        assert after["latest_capture_id"] > before and after["records"] == 11
        recs = api.get_period(s, "TD-SECURITIES", "2026-10")
        everything = api.get_period(s, "TD-SECURITIES", "2026-10", include_superseded=True)
    assert len(recs) == 11 and len(everything) == 12
    revised = [r for r in everything if r["source_key"] == f"{doc[1]['cusip']}/{doc[1]['issueDate'][:10]}"]
    assert [json.loads(r["fields_json"])["highDiscountRate"] for r in revised] == ["", "3.880000"]
    assert revised[0]["valid_to"] and not revised[1]["valid_to"]


def test_mspd_records_and_totals(migrated_db):
    _capture("FD-MSPD-STRIPS", "2026-09", MSPD_SEP)
    with db.session() as s:
        recs = api.get_period(s, "FD-MSPD-STRIPS", "2026-09")
    assert len(recs) == 410 and sum(r["record_type"] == "stripped_total" for r in recs) == 4


def test_unknown_source(migrated_db):
    with db.session() as s, pytest.raises(api.UnknownSource):
        api.list_periods(s, "TD-PRICES")
