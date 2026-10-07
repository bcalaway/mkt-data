"""Near-raw records for other services (proto/records.proto, docs/phase-3.md step 2).

Plain functions returning plain dicts, tested without gRPC;
app/grpc_server.py's Records service turns them into messages. Read by
period, like Observations (app/rates/api.py): secmaster-svc lists a source's
periods, re-reads the ones whose latest_capture_id moved, and keeps its own
watermark per period. A revision or a dropped record always moves it, for
the same reason as there: either one comes only from a newer capture of the
same period.
"""

import json

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.models import Record, Source
from app.securities.sources import SOURCES as ALL_SOURCES

SOURCES = {name: src for name, src in ALL_SOURCES.items() if src.shape == "records"}


class UnknownSource(LookupError):
    pass


def _iso(v) -> str:
    return v.isoformat() if v is not None else ""


def _source_id(s: Session, name: str) -> int | None:
    if name not in SOURCES:
        raise UnknownSource(f"unknown record source {name!r}; known: {sorted(SOURCES)}")
    return s.scalar(select(Source.id).where(Source.name == name))


def list_sources(s: Session) -> list[dict]:
    out = []
    for name, src in SOURCES.items():
        sid = _source_id(s, name)
        periods = 0
        if sid is not None:
            periods = s.scalar(select(func.count(func.distinct(Record.period))).where(Record.source_id == sid)) or 0
        out.append({"name": name, "description": src.spec.description, "calendar": src.calendar,
                    "first_period": src.first_period, "periods": periods})
    return out


def list_periods(s: Session, name: str, since_period: str = "") -> list[dict]:
    sid = _source_id(s, name)
    if sid is None:
        return []
    q = (
        select(
            Record.period, func.max(Record.capture_id),
            func.count().filter(Record.valid_to.is_(None)),
            func.min(Record.as_of).filter(Record.valid_to.is_(None)),
            func.max(Record.as_of).filter(Record.valid_to.is_(None)),
        )
        .where(Record.source_id == sid)
        .group_by(Record.period)
        .order_by(Record.period)
    )
    if since_period:
        q = q.where(Record.period >= since_period)
    return [
        {"period": p, "latest_capture_id": cap, "records": n, "first_date": _iso(first), "last_date": _iso(last)}
        for p, cap, n, first, last in s.execute(q)
    ]


def get_period(s: Session, name: str, period: str, include_superseded: bool = False) -> list[dict]:
    sid = _source_id(s, name)
    if sid is None:
        return []
    q = select(Record).where(Record.source_id == sid, Record.period == period)
    if not include_superseded:
        q = q.where(Record.valid_to.is_(None))
    return [
        {
            "id": r.id, "record_type": r.record_type, "source_key": r.source_key, "as_of": r.as_of.isoformat(),
            "fields_json": json.dumps(r.fields, ensure_ascii=False, sort_keys=True), "capture_id": r.capture_id,
            "valid_from": _iso(r.valid_from), "valid_to": _iso(r.valid_to),
        }
        for r in s.scalars(q.order_by(Record.as_of, Record.record_type, Record.source_key, Record.id))
    ]
