"""Near-raw calendar data for other services (docs/phase-2.md, Part A).

Plain functions returning plain dicts, so the rules are tested without
gRPC; app/grpc_server.py's CalendarSources turns them into messages.
"""

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.calendars import service
from app.models import Capture, Source, SourceDay, SourceYear


class UnknownSource(LookupError):
    pass


def _iso(dt) -> str:
    return dt.isoformat() if dt is not None else ""


def _calendar_of() -> dict[str, str]:
    return {src.name: cal.name for cal in service.CALENDARS.values() for src in cal.sources}


def _info(s: Session, name: str, calendar: str, src: Source | None) -> dict:
    spec = service.SOURCES.get(name)
    out = {
        "name": name, "calendar": calendar,
        "url": spec.url if spec else (src.url if src else ""),
        "description": spec.description if spec else (src.description if src else ""),
        "parsed": spec is not None and spec.parse is not None,
        "latest_capture_id": 0, "latest_capture_at": "", "latest_applied_capture_id": 0,
    }
    if src is None:
        return out
    latest = s.execute(
        select(Capture.id, Capture.fetched_at).where(Capture.source_id == src.id).order_by(Capture.id.desc()).limit(1)
    ).first()
    if latest is not None:
        out["latest_capture_id"], out["latest_capture_at"] = latest.id, _iso(latest.fetched_at)
    applied = max(
        s.scalar(select(func.max(SourceDay.capture_id)).where(SourceDay.source_id == src.id)) or 0,
        s.scalar(select(func.max(SourceYear.capture_id)).where(SourceYear.source_id == src.id)) or 0,
    )
    out["latest_applied_capture_id"] = applied
    return out


def list_sources(s: Session) -> list[dict]:
    """Every calendar source, in each calendar's precedence order (FED, SIFMA-US, NYSE)."""
    by_name = {x.name: x for x in s.scalars(select(Source))}
    return [
        _info(s, src.name, cal.name, by_name.get(src.name))
        for cal in service.CALENDARS.values()
        for src in cal.sources
    ]


def source_rows(s: Session, name: str, include_superseded: bool = False) -> dict:
    """One source's near-raw years and days (current, plus superseded if asked), by date."""
    calendar = _calendar_of().get(name)
    if calendar is None:
        raise UnknownSource(f"unknown calendar source {name!r}")
    src = s.scalar(select(Source).where(Source.name == name))
    out = {"source": _info(s, name, calendar, src), "years": [], "days": []}
    if src is None:
        return out
    out["years"] = [
        {"year": y.year, "capture_id": y.capture_id, "first_seen_at": _iso(y.first_seen_at)}
        for y in s.scalars(select(SourceYear).where(SourceYear.source_id == src.id).order_by(SourceYear.year))
    ]
    q = select(SourceDay).where(SourceDay.source_id == src.id)
    if not include_superseded:
        q = q.where(SourceDay.valid_to.is_(None))
    out["days"] = [
        {
            "day": d.day.isoformat(), "status": d.status,
            "close_time": d.close_time.strftime("%H:%M") if d.close_time else "",
            "holiday": d.holiday, "capture_id": d.capture_id,
            "valid_from": _iso(d.valid_from), "valid_to": _iso(d.valid_to),
        }
        for d in s.scalars(q.order_by(SourceDay.day, SourceDay.valid_from))
    ]
    return out
