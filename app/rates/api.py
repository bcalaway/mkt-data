"""Near-raw observations for other services (proto/observations.proto, phase 2 Part B, phase 3).

Plain functions returning plain dicts, tested without gRPC;
app/grpc_server.py's Observations service turns them into messages. Read by
period: quote-svc lists a source's periods, re-reads the ones whose
latest_capture_id moved, and keeps its own watermark per period. A revision
or a dropped value always moves it: a revision inserts a row from the newer
capture, and a dropped value is only possible in a newer capture of the same
month, whose other values it then carries.

Every observation-shaped source is served: the CMT yields (phase 2) and,
from phase 3, FedInvest's prices (TD-PRICES, a period per day) and BLS's
CPI (BLS-CPI, a period per year). Record-shaped sources are in
app/securities/api.py (proto/records.proto).
"""

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.models import Observation, Source
from app.rates.sources import SOURCES as RATE_SOURCES
from app.securities.sources import SOURCES as SECURITIES_SOURCES

# name -> (description, calendar, first_period)
SOURCES = {name: (src.spec.description, src.calendar, src.first_period) for name, src in RATE_SOURCES.items()} | {
    name: (src.spec.description, src.calendar, src.first_period)
    for name, src in SECURITIES_SOURCES.items() if src.shape == "observations"
}


class UnknownSource(LookupError):
    pass


def _iso(v) -> str:
    return v.isoformat() if v is not None else ""


def _source_id(s: Session, name: str) -> int | None:
    if name not in SOURCES:
        raise UnknownSource(f"unknown observation source {name!r}; known: {sorted(SOURCES)}")
    return s.scalar(select(Source.id).where(Source.name == name))


def list_sources(s: Session) -> list[dict]:
    out = []
    for name, (description, calendar, first_period) in SOURCES.items():
        sid = _source_id(s, name)
        periods = 0
        if sid is not None:
            periods = s.scalar(
                select(func.count(func.distinct(Observation.period))).where(Observation.source_id == sid)
            ) or 0
        out.append({"name": name, "description": description, "calendar": calendar,
                    "first_period": first_period, "periods": periods})
    return out


def list_periods(s: Session, name: str, since_period: str = "") -> list[dict]:
    sid = _source_id(s, name)
    if sid is None:
        return []
    q = (
        select(
            Observation.period, func.max(Observation.capture_id),
            func.count().filter(Observation.valid_to.is_(None)),
            func.min(Observation.as_of).filter(Observation.valid_to.is_(None)),
            func.max(Observation.as_of).filter(Observation.valid_to.is_(None)),
        )
        .where(Observation.source_id == sid)
        .group_by(Observation.period)
        .order_by(Observation.period)
    )
    if since_period:
        q = q.where(Observation.period >= since_period)
    return [
        {"period": p, "latest_capture_id": cap, "values": n, "first_date": _iso(first), "last_date": _iso(last)}
        for p, cap, n, first, last in s.execute(q)
    ]


def get_period(s: Session, name: str, period: str, include_superseded: bool = False) -> list[dict]:
    sid = _source_id(s, name)
    if sid is None:
        return []
    q = select(Observation).where(Observation.source_id == sid, Observation.period == period)
    if not include_superseded:
        q = q.where(Observation.valid_to.is_(None))
    return [
        {
            "id": r.id, "source_key": r.source_key, "as_of": r.as_of.isoformat(), "field": r.field,
            "value": format(r.value, "f"), "unit": r.unit, "capture_id": r.capture_id,
            "valid_from": _iso(r.valid_from), "valid_to": _iso(r.valid_to),
        }
        for r in s.scalars(q.order_by(Observation.as_of, Observation.source_key, Observation.id))
    ]
