"""Near-raw records and observations for the Treasury securities sources (phase 3, step 2)."""

import json
from datetime import UTC, date, datetime, timedelta
from decimal import Decimal

import pytest
from sqlalchemy import func, select

from app import db
from app.calendars.parsed import ParseError
from app.models import Capture, Observation, Record
from app.rates.near_raw import in_period
from app.securities import sources as sec
from tests.conftest import FIXTURES

TD_OCT = (FIXTURES / "td_securities_2026_10_capture1261.json").read_bytes()
PRICES_OCT5 = (FIXTURES / "td_prices_2026_10_05_capture1270.html").read_bytes()


def _fetcher(body: bytes):
    return lambda url: (200, "application/json", body)


def _current(s, model, **where):
    q = select(model).where(model.valid_to.is_(None))
    for k, v in where.items():
        q = q.where(getattr(model, k) == v)
    return s.scalars(q).all()


def test_in_period():
    d = date(2026, 10, 5)
    assert in_period(d, "2026-10-05") and in_period(d, "2026-10") and in_period(d, "2026")
    assert not in_period(d, "2026-10-06") and not in_period(d, "2026-09") and not in_period(d, "2025")


def test_records_revisions_and_removals(migrated_db):
    doc = json.loads(TD_OCT)
    with db.session() as s:
        first = sec.run_capture(s, "TD-SECURITIES", "2026-10", _fetcher(TD_OCT))
        assert (first["records"], first["added"], first["changed"], first["removed"]) == (11, 11, 0, 0)
        # Results come in for one auction (a field changes), another drops out.
        k = next(i for i, r in enumerate(doc) if r["cusip"] == "912810UW6")
        doc[k] = doc[k] | {"highYield": "4.912000"}
        gone = doc.pop(k + 1 if k == 0 else 0)
        r = sec.run_capture(s, "TD-SECURITIES", "2026-10", _fetcher(json.dumps(doc).encode()))
        assert (r["records"], r["added"], r["changed"], r["removed"]) == (10, 0, 1, 1)
        rows = s.scalars(select(Record).where(Record.source_key == "912810UW6/2026-10-15").order_by(Record.id)).all()
        assert [x.fields["highYield"] for x in rows] == ["", "4.912000"]
        assert rows[0].valid_to is not None and rows[1].valid_to is None
        dropped = f"{gone['cusip']}/{gone['issueDate'][:10]}"
        assert not _current(s, Record, source_key=dropped)
        # Another month is left alone.
        sec.run_capture(s, "TD-SECURITIES", "2026-09", _fetcher(b"[]"))
        assert len(_current(s, Record)) == 10


def test_record_rebuild_gives_the_same_rows(migrated_db):
    doc = json.loads(TD_OCT)
    with db.session() as s:
        sec.run_capture(s, "TD-SECURITIES", "2026-10", _fetcher(TD_OCT))
        doc[0] = doc[0] | {"bidToCoverRatio": "2.61"}
        sec.run_capture(s, "TD-SECURITIES", "2026-10", _fetcher(json.dumps(doc).encode()))
        before = sorted((x.source_key, x.capture_id, str(x.valid_from), str(x.valid_to))
                        for x in s.scalars(select(Record)))
        out = sec.run_rebuild(s, "TD-SECURITIES")
        after = sorted((x.source_key, x.capture_id, str(x.valid_from), str(x.valid_to))
                       for x in s.scalars(select(Record)))
    assert out["current_records"] == 11 and out["applied"] == 2 and before == after


def test_prices_end_of_day_arrives_the_next_day(migrated_db, monkeypatch):
    """The evening of the 5th: buy and sell, no end of day. The next evening: the same page with end of day."""
    no_eod = PRICES_OCT5.replace(b"<td>92.250000</td>", b"<td>0.000000</td>")
    monkeypatch.setattr(sec, "post_fedinvest", lambda period: _fetcher(no_eod))
    with db.session() as s:
        first = sec.run_capture(s, "TD-PRICES", "2026-10-05")
        cap = s.get(Capture, first["capture_id"])
        cap.fetched_at = datetime.now(UTC) - timedelta(days=1)
        s.commit()
        monkeypatch.setattr(sec, "post_fedinvest", lambda period: _fetcher(PRICES_OCT5))
        r = sec.run_capture(s, "TD-PRICES", "2026-10-05")
        n = PRICES_OCT5.count(b"<td>92.250000</td>")  # the real page has this price in more than one row
        assert r["new_capture"] and (r["added"], r["changed"], r["removed"]) == (n, 0, 0)
        eod = _current(s, Observation, source_key="912810UW6", field="eod")
        assert len(eod) == 1 and eod[0].value == Decimal("92.25") and eod[0].capture_id == r["capture_id"]


def test_a_price_page_for_another_day_is_refused(migrated_db, monkeypatch):
    monkeypatch.setattr(sec, "post_fedinvest", lambda period: _fetcher(PRICES_OCT5))
    with db.session() as s:
        with pytest.raises(ParseError, match="outside the capture's period 2026-10-06"):
            sec.run_capture(s, "TD-PRICES", "2026-10-06")
        assert s.scalar(select(func.count()).select_from(Observation)) == 0
