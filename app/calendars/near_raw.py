"""Near-raw calendar rows: each source's parse as that source states it (docs/phase-2.md, Part A).

mkt-data is the ingestion layer: it captures every source raw and parses
each capture into `source_year` and `source_day`, one set of rows per source.
No precedence and no projection rules apply here: two sources listing the
same date both keep their row, and a projected source keeps every year it
generates. Building one calendar out of its sources is calendar-svc's job.

History works as phase 1's calendar_day did: within the years a capture covers, a new
date is inserted, a changed date gets a new row (the old one gets
`valid_to`), and a date no longer listed is closed off. Years a source stops
listing are left alone. Times come from the captures (`fetched_at`), not the
clock, so replaying every capture from raw (`rebuild`) gives the same rows.
"""

from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from app.calendars.parsed import Day, ParsedCalendar, ParseError, diff
from app.models import Capture, Source, SourceDay, SourceYear


def apply_source(s: Session, cap: Capture, parsed: ParsedCalendar) -> dict:
    """Record one capture's parse as its source's near-raw rows. Flushes, doesn't commit."""
    at = cap.fetched_at
    rows = s.scalars(
        select(SourceDay).where(SourceDay.source_id == cap.source_id, SourceDay.valid_to.is_(None))
    ).all()
    by_day = {r.day: r for r in rows}
    current = {r.day: Day(r.day, r.status, r.holiday, r.close_time) for r in rows}
    d = diff(current, parsed)
    for day in [x.day for x in d.changed] + list(d.removed):
        by_day[day].valid_to = at
    s.flush()  # close old versions before inserting new ones (unique current row)
    for x in d.added + d.changed:
        s.add(
            SourceDay(
                source_id=cap.source_id, day=x.day, status=x.status, close_time=x.close_time,
                holiday=x.holiday, capture_id=cap.id, valid_from=at,
            )
        )
    years = {y.year: y for y in s.scalars(select(SourceYear).where(SourceYear.source_id == cap.source_id))}
    new_years = []
    for y in parsed.years:
        row = years.get(y)
        if row is None:
            s.add(SourceYear(source_id=cap.source_id, year=y, capture_id=cap.id, first_seen_at=at))
            new_years.append(y)
        else:
            row.capture_id = cap.id
    s.flush()
    return {"new_years": len(new_years), "added": len(d.added), "changed": len(d.changed), "removed": len(d.removed)}


def rebuild(s: Session, source_name: str, parse) -> dict:
    """Rebuild one source's near-raw rows by replaying all its captures, oldest first.

    Processed rows are always rebuildable from raw; this is how near-raw is
    first filled from captures taken before it existed, and how a parser fix
    is applied to the whole history. A capture that fails to parse is
    skipped and reported, like a capture job's 422: the next one carries on.
    Commits.
    """
    src = s.scalar(select(Source).where(Source.name == source_name))
    if src is None:
        return {"source": source_name, "captures": 0, "skipped": "nothing captured yet"}
    s.execute(delete(SourceDay).where(SourceDay.source_id == src.id))
    s.execute(delete(SourceYear).where(SourceYear.source_id == src.id))
    s.flush()
    caps = s.scalars(select(Capture).where(Capture.source_id == src.id).order_by(Capture.id)).all()
    failed = []
    for cap in caps:
        try:
            parsed = parse(cap.body)
        except ParseError as e:
            failed.append({"capture_id": cap.id, "error": str(e)[:500]})
            continue
        apply_source(s, cap, parsed)
    s.commit()
    out = {"source": source_name, "captures": len(caps), "applied": len(caps) - len(failed)} | counts(s, src.id)
    if failed:
        out["parse_failed"] = failed
    return out


def counts(s: Session, source_id: int) -> dict:
    current = s.scalars(
        select(SourceDay.day).where(SourceDay.source_id == source_id, SourceDay.valid_to.is_(None))
    ).all()
    superseded = s.scalars(
        select(SourceDay.id).where(SourceDay.source_id == source_id, SourceDay.valid_to.is_not(None))
    ).all()
    years = s.scalars(select(SourceYear.year).where(SourceYear.source_id == source_id)).all()
    return {
        "years": len(years),
        "first_year": min(years, default=None),
        "last_year": max(years, default=None),
        "current_days": len(current),
        "superseded_days": len(superseded),
    }


def current_days(s: Session, source_name: str) -> list[Day]:
    """A source's current near-raw days, by date."""
    rows = s.scalars(
        select(SourceDay)
        .join(Source, Source.id == SourceDay.source_id)
        .where(Source.name == source_name, SourceDay.valid_to.is_(None))
        .order_by(SourceDay.day)
    ).all()
    return [Day(r.day, r.status, r.holiday, r.close_time) for r in rows]


def years(s: Session, source_name: str) -> list[int]:
    return sorted(
        s.scalars(select(SourceYear.year).join(Source, Source.id == SourceYear.source_id).where(Source.name == source_name))
    )

