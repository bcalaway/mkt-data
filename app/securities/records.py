"""Near-raw records: each source's records as it publishes them (docs/phase-3.md, step 2).

The same rules as near-raw observations (app/rates/near_raw.py), for records:
a capture covers one period, and within it a new record is inserted, a
changed one (any field) closes the old row (`valid_to`) and adds a new one (a
revision), and a record the source no longer lists is closed off. Other
periods are left alone. Times are the captures' fetch times, so replaying
every capture (`rebuild`) gives the same rows. secmaster-svc reads these.
"""

from sqlalchemy import delete, func, select
from sqlalchemy.orm import Session

from app.calendars.parsed import ParseError
from app.models import Capture, Record, Source
from app.rates.near_raw import in_period
from app.securities.parsers import Rec


def apply_period(s: Session, cap: Capture, recs: list[Rec]) -> dict:
    """Record one capture's records for its source and period. Flushes, doesn't commit."""
    at = cap.fetched_at
    rows = s.scalars(
        select(Record).where(Record.source_id == cap.source_id, Record.period == cap.period, Record.valid_to.is_(None))
    ).all()
    current = {(r.record_type, r.source_key): r for r in rows}
    new = {(r.record_type, r.source_key): r for r in recs}
    if len(new) != len(recs):
        raise ParseError("the same record appears twice")
    outside = [r for r in recs if not in_period(r.as_of, cap.period)]
    if outside:
        raise ParseError(
            f"{len(outside)} records fall outside the capture's period {cap.period} "
            f"(first: {outside[0].source_key} on {outside[0].as_of})"
        )
    added = changed = 0
    to_close = [r for k, r in current.items() if k not in new]
    for k, rec in new.items():
        old = current.get(k)
        if old is None:
            added += 1
        elif old.fields != rec.fields or old.as_of != rec.as_of:
            changed += 1
            to_close.append(old)
    for r in to_close:
        r.valid_to = at
    s.flush()  # close old versions before inserting new ones (unique current row)
    for k, rec in new.items():
        old = current.get(k)
        if old is None or old.valid_to is not None:
            s.add(Record(
                source_id=cap.source_id, period=cap.period, record_type=rec.record_type, source_key=rec.source_key,
                as_of=rec.as_of, fields=rec.fields, capture_id=cap.id, valid_from=at,
            ))
    s.flush()
    last = max((r.as_of for r in recs), default=None)
    return {"records": len(new), "last_date": last.isoformat() if last else None,
            "added": added, "changed": changed, "removed": len(to_close) - changed}


def rebuild(s: Session, source_name: str, parse) -> dict:
    """Rebuild one source's records by replaying all its captures, oldest first. Commits.

    As near_raw.rebuild: one transaction, captures read one at a time, a
    capture that fails to parse skipped and reported.
    """
    src_id = s.scalar(select(Source.id).where(Source.name == source_name))
    if src_id is None:
        return {"source": source_name, "captures": 0, "skipped": "nothing captured yet"}
    s.execute(delete(Record).where(Record.source_id == src_id))
    s.flush()
    cap_ids = s.scalars(select(Capture.id).where(Capture.source_id == src_id, Capture.period.is_not(None))
                        .order_by(Capture.id)).all()
    failed = []
    for cap_id in cap_ids:
        cap = s.get(Capture, cap_id)
        try:
            apply_period(s, cap, parse(cap.body))
        except ParseError as e:
            failed.append({"capture_id": cap.id, "period": cap.period, "error": str(e)[:500]})
        s.flush()
        s.expunge_all()
    s.commit()
    n, first, last = s.execute(
        select(func.count(), func.min(Record.as_of), func.max(Record.as_of))
        .where(Record.source_id == src_id, Record.valid_to.is_(None))
    ).one()
    out = {"source": source_name, "captures": len(cap_ids), "applied": len(cap_ids) - len(failed),
           "current_records": n, "first_date": first, "last_date": last}
    if failed:
        out["parse_failed"] = failed
    return out
