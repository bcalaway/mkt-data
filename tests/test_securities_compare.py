"""TreasuryDirect's auction records against Fiscal Data's (app/securities/compare.py), on real captures."""

from datetime import UTC, datetime
from decimal import Decimal
from pathlib import Path

from app.securities import compare
from app.securities.parsers import parse_fd_auctions, parse_td_securities

FIXTURES = Path(__file__).parent / "fixtures"


def _by_key(recs):
    return {r.source_key: r.fields for r in recs if r.record_type == "auction"}


def _october():
    td = _by_key(parse_td_securities((FIXTURES / "td_securities_2026_10_capture1261.json").read_bytes()))
    fd = _by_key(parse_fd_auctions((FIXTURES / "fd_auctions_2026_10_capture1263.json").read_bytes()))
    return td, fd


def test_norm_keeps_meaning_and_drops_presentation():
    assert compare.norm("2026-10-15T00:00:00") == compare.norm("2026-10-15") == "2026-10-15"
    assert compare.norm("") is compare.norm("null") is compare.norm(None) is None
    assert compare.norm("4.250000") == compare.norm("4.25") == Decimal("4.25")
    assert compare.norm("1,000") == Decimal(1000)
    assert compare.norm("Yes") == compare.norm("true") == "yes"
    assert compare.norm(" 10-Year ") == compare.norm("10-year")
    assert compare.norm("4.25") != compare.norm("4.26")


def test_fields_pair_by_snake_case_or_alias_and_skip_page_fields():
    pairs = dict(compare.field_pairs(["interestRate", "cusip", "pdfFilenameAnnouncement", "updatedTimestamp", "offeringAmount"],
                                     ["int_rate", "cusip", "pdf_filenm_announcemt", "offering_amt"]))
    assert pairs == {"interestRate": "int_rate", "cusip": "cusip", "offeringAmount": "offering_amt"}


def test_the_october_2026_captures_agree():
    # The same 11 auctions under the same keys (docs/phase-3.md, step 2): every shared field agrees once
    # presentation is set aside.
    td, fd = _october()
    out = compare.compare(td, fd)
    assert out["compared"] == 11 and out["only_left"] == [] and out["only_right"] == []
    assert out["fields_compared"] > 80
    assert [f for f in out["fields"] if f["different"]] == []


def test_a_difference_and_a_one_sided_record_are_reported():
    td, fd = _october()
    key = next(k for k in sorted(td) if td[k].get("offeringAmount") and td[k].get("maturityDate"))
    fd[key] = dict(fd[key], maturity_date="2099-01-01", offering_amt="null")
    td["912999ZZ9/2026-10-31"] = dict(td[key])
    out = compare.compare(td, fd)
    assert out["only_left"] == ["912999ZZ9/2026-10-31"] and out["records_differing"] == 1
    by = {f["field"]: f for f in out["fields"]}
    assert by["maturityDate"]["different"] == 1 and by["maturityDate"]["examples"][0]["FD-AUCTIONS"] == "2099-01-01"
    assert by["offeringAmount"]["one_side_empty"] == 1 and by["offeringAmount"]["different"] == 0


def test_run_keeps_the_latest_result(migrated_db):
    from app import db
    from app.models import RecordComparison

    with db.session() as s:
        first = compare.run(s, datetime(2026, 10, 7, tzinfo=UTC))
        compare.run(s, datetime(2026, 10, 8, tzinfo=UTC))
        rows = s.query(RecordComparison).all()
    assert first["compared"] == 0 and len(rows) == 1 and rows[0].ran_at.day == 8
