"""Near-raw observations: each CMT source's values as that source publishes them.

A capture covers one month (its period); its parse is that month's values.
Within the period: a new value is inserted, a changed value closes the old
row (`valid_to`) and adds a new one (a revision), and a value the source no
longer lists is closed off. Other months are left alone. Times are the
captures' fetch times, so replaying every capture (`rebuild`) gives the same
rows. quote-svc reads these and builds golden quotes (docs/phase-2.md).
"""

from sqlalchemy import delete, func, select
from sqlalchemy.orm import Session

from app.calendars.parsed import ParseError
from app.models import Capture, Observation, Source
from app.rates.parsers import Obs


def apply_period(s: Session, cap: Capture, obs: list[Obs]) -> dict:
    """Record one capture's observations for its source and period. Flushes, doesn't commit."""
    at = cap.fetched_at
    rows = s.scalars(
        select(Observation).where(
            Observation.source_id == cap.source_id, Observation.period == cap.period, Observation.valid_to.is_(None)
        )
    ).all()
    current = {(r.source_key, r.as_of, r.field): r for r in rows}
    new = {(o.source_key, o.as_of, o.field): o for o in obs}
    if len(new) != len(obs):
        raise ParseError("the same series, date and field appears twice")
    outside = [k for k in new if f"{k[1]:%Y-%m}" != cap.period]
    if outside:
        raise ParseError(f"{len(outside)} values fall outside the capture's month {cap.period} (first: {outside[0][1]})")
    added = changed = 0
    to_close = [r for k, r in current.items() if k not in new]
    for k, o in new.items():
        old = current.get(k)
        if old is None:
            added += 1
        elif old.value != o.value or old.unit != o.unit:
            changed += 1
            to_close.append(old)
    for r in to_close:
        r.valid_to = at
    s.flush()  # close old versions before inserting new ones (unique current row)
    for k, o in new.items():
        old = current.get(k)
        if old is None or old.valid_to is not None:
            s.add(Observation(
                source_id=cap.source_id, period=cap.period, source_key=o.source_key, as_of=o.as_of, field=o.field,
                value=o.value, unit=o.unit, capture_id=cap.id, valid_from=at,
            ))
    s.flush()
    return {"values": len(new), "days": len({k[1] for k in new}), "added": added, "changed": changed,
            "removed": len(to_close) - changed}


def rebuild(s: Session, source_name: str, parse) -> dict:
    """Rebuild one source's observations by replaying all its captures, oldest first. Commits.

    A capture that fails to parse is skipped and reported; the next one carries on.
    One transaction, so readers never see a half-rebuilt history, but captures
    are read one at a time and the session is cleared after each: the full
    UST-PAR history is about 100,000 rows, too many to hold in a 256 MB container.
    """
    src_id = s.scalar(select(Source.id).where(Source.name == source_name))
    if src_id is None:
        return {"source": source_name, "captures": 0, "skipped": "nothing captured yet"}
    s.execute(delete(Observation).where(Observation.source_id == src_id))
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
        select(func.count(), func.min(Observation.as_of), func.max(Observation.as_of))
        .where(Observation.source_id == src_id, Observation.valid_to.is_(None))
    ).one()
    out = {"source": source_name, "captures": len(cap_ids), "applied": len(cap_ids) - len(failed),
           "current_values": n, "first_date": first, "last_date": last}
    if failed:
        out["parse_failed"] = failed
    return out
