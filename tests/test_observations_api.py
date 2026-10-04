"""The Observations read API (proto/observations.proto, phase 2 Part B): what quote-svc pulls."""

from decimal import Decimal

import pytest

from app import db
from app.rates import api
from app.rates import sources as rates
from tests.conftest import FIXTURES

UST_SEP = (FIXTURES / "ust_par_2026_09_capture31.xml").read_bytes()
UST_OCT = (FIXTURES / "ust_par_2026_10_capture32.xml").read_bytes()
REVISED_OCT = UST_OCT.replace(
    b'<d:BC_10YEAR m:type="Edm.Double">5.24</d:BC_10YEAR>', b'<d:BC_10YEAR m:type="Edm.Double">5.25</d:BC_10YEAR>', 1
).replace(b'<d:BC_1_5MONTH m:type="Edm.Double">4.10</d:BC_1_5MONTH>', b"", 1)


def _fetcher(body: bytes):
    return lambda url: (200, "text/xml", body)


def _capture(period: str, body: bytes):
    with db.session() as s:
        rates.run_capture(s, "UST-PAR", period, _fetcher(body))


def test_sources_are_listed_before_anything_is_captured(migrated_db):
    with db.session() as s:
        listed = {r["name"]: r for r in api.list_sources(s)}
        assert api.list_periods(s, "UST-PAR") == []
        assert api.get_period(s, "UST-PAR", "2026-09") == []
    assert set(listed) == {"UST-PAR", "H15-TCM"}
    assert listed["UST-PAR"]["calendar"] == "SIFMA-US" and listed["UST-PAR"]["first_period"] == "1990-01"
    assert listed["UST-PAR"]["periods"] == 0


def test_periods_list_counts_and_dates(migrated_db):
    _capture("2026-09", UST_SEP)
    _capture("2026-10", UST_OCT)
    with db.session() as s:
        periods = api.list_periods(s, "UST-PAR")
        since = api.list_periods(s, "UST-PAR", "2026-10")
        listed = {r["name"]: r for r in api.list_sources(s)}
    assert [(p["period"], p["values"]) for p in periods] == [("2026-09", 294), ("2026-10", 28)]
    assert periods[0]["first_date"] == "2026-09-01" and periods[0]["last_date"] == "2026-09-30"
    assert [p["period"] for p in since] == ["2026-10"]
    assert listed["UST-PAR"]["periods"] == 2


def test_a_revision_moves_the_periods_latest_capture(migrated_db):
    _capture("2026-09", UST_SEP)
    _capture("2026-10", UST_OCT)
    with db.session() as s:
        before = {p["period"]: p["latest_capture_id"] for p in api.list_periods(s, "UST-PAR")}
    _capture("2026-10", REVISED_OCT)
    with db.session() as s:
        after = {p["period"]: p for p in api.list_periods(s, "UST-PAR")}
    assert after["2026-09"]["latest_capture_id"] == before["2026-09"]  # untouched month
    assert after["2026-10"]["latest_capture_id"] > before["2026-10"]
    assert after["2026-10"]["values"] == 27  # one dropped


def test_get_period_current_and_superseded(migrated_db):
    _capture("2026-10", UST_OCT)
    _capture("2026-10", REVISED_OCT)
    with db.session() as s:
        current = api.get_period(s, "UST-PAR", "2026-10")
        everything = api.get_period(s, "UST-PAR", "2026-10", include_superseded=True)
    ten = [v for v in current if v["source_key"] == "BC_10YEAR" and v["as_of"] == "2026-10-01"]
    assert len(ten) == 1 and Decimal(ten[0]["value"]) == Decimal("5.25") and ten[0]["unit"] == "percent" and ten[0]["valid_to"] == ""
    assert not any(v["source_key"] == "BC_1_5MONTH" and v["as_of"] == "2026-10-01" for v in current)
    assert len(current) == 27 and len(everything) == 29  # + the old 10Y and the dropped 1.5M
    old = [v for v in everything if v["source_key"] == "BC_10YEAR" and v["as_of"] == "2026-10-01" and v["valid_to"]]
    assert Decimal(old[0]["value"]) == Decimal("5.24") and old[0]["valid_to"] == ten[0]["valid_from"]
    # Decimal strings, never floats or exponents. (Postgres keeps the printed scale, "4.10";
    # the tests' SQLite pads it, so compare as Decimals.)
    assert all("e" not in v["value"].lower() for v in everything)
    assert any(Decimal(v["value"]) == Decimal("4.10") for v in everything)


def test_unknown_source(migrated_db):
    with db.session() as s, pytest.raises(api.UnknownSource):
        api.list_periods(s, "FED-K8")
