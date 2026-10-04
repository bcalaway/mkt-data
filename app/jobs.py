"""Job API for Airflow (ADR-0031 in nyc_pa_aws_gitops).

Airflow's DAGs call these over the home-platform network; the work runs
here, in this app's own container. Every endpoint:

- requires `Authorization: Bearer <AIRFLOW_TOKEN>` (other apps and previews
  share the network). The GET endpoints, which only read, also accept
  READ_TOKEN, home-mcp's read-only token,
- is idempotent for its inputs (Airflow retries),
- answers with a JSON summary that shows up in the Airflow task log.

Errors come back as JSON with a reason, and with a status Airflow treats as
a failure: 502 when the upstream source can't be fetched, 422 when its
content can't be parsed (the raw capture is kept), 409 when a date isn't
covered by any published calendar year.
"""

import hmac
from datetime import date

from fastapi import APIRouter, Depends, Header, HTTPException, Query, Response
from sqlalchemy import select

from app import db
from app.calendars import service, text
from app.calendars.parsed import ParseError
from app.config import settings
from app.models import CalendarDay, CalendarYear, Capture, Source

router = APIRouter(prefix="/jobs")


def require_token(authorization: str | None = Header(default=None)) -> None:
    if not settings.airflow_token:
        raise HTTPException(503, "job API disabled: AIRFLOW_TOKEN isn't set")
    if not hmac.compare_digest(_bearer(authorization), settings.airflow_token.encode()):
        raise HTTPException(401, "bad or missing job token")


def _bearer(authorization: str | None) -> bytes:
    return (authorization or "").removeprefix("Bearer ").strip().encode()


def require_read_token(authorization: str | None = Header(default=None)) -> None:
    """The Airflow token, or the read-only token. For GET endpoints only."""
    tokens = [t for t in (settings.airflow_token, settings.read_token) if t]
    if not tokens:
        raise HTTPException(503, "job API disabled: no AIRFLOW_TOKEN or READ_TOKEN set")
    given = _bearer(authorization)
    # Compare against every token (no early exit), so timing doesn't say which matched.
    matches = [hmac.compare_digest(given, t.encode()) for t in tokens]
    if not any(matches):
        raise HTTPException(401, "bad or missing token")


def _calendar(name: str) -> str:
    key = name.upper()
    if key not in service.CALENDARS:
        raise HTTPException(404, f"unknown calendar {name!r}; known: {sorted(service.CALENDARS)}")
    return key


@router.post("/calendars/{name}/capture", dependencies=[Depends(require_token)])
def capture_calendar(name: str) -> dict:
    """Fetch the calendar's source, keep it raw if new, and apply the parse."""
    key = _calendar(name)
    try:
        with db.session() as s:
            return service.run_capture(s, key)
    except service.SourceFetchError as e:
        raise HTTPException(502, f"fetch failed: {e}") from None
    except ParseError as e:
        raise HTTPException(422, f"parse failed (raw capture kept): {e}") from None


@router.post("/calendars/{name}/reparse", dependencies=[Depends(require_token)])
def reparse_calendar(name: str) -> dict:
    """Re-apply the latest stored capture, e.g. after a parser fix. No fetch."""
    key = _calendar(name)
    try:
        with db.session() as s:
            return service.run_reparse(s, key)
    except service.NotCovered as e:
        raise HTTPException(409, str(e)) from None
    except ParseError as e:
        raise HTTPException(422, f"parse failed: {e}") from None


@router.get("/calendars/{name}/business-day", dependencies=[Depends(require_read_token)])
def business_day(name: str, on: date) -> dict:
    """Is `on` a business day for this calendar? For DAGs' short-circuit first task."""
    key = _calendar(name)
    try:
        with db.session() as s:
            return service.business_day(s, key, on)
    except service.NotCovered as e:
        raise HTTPException(409, str(e)) from None


# Raw captures, read-only: for turning a real capture into a test fixture,
# or checking what a parser saw. home-mcp's mkt_data_captures and
# mkt_data_capture_text tools read these with the read-only token.


@router.get("/captures", dependencies=[Depends(require_read_token)])
def list_captures(
    source: str | None = None, calendar: str | None = None, limit: int = Query(20, ge=1, le=200)
) -> dict:
    """Newest captures first, metadata only. Filter by source or calendar name."""
    if source and calendar:
        raise HTTPException(400, "give source or calendar, not both")
    names = [source.upper()] if source else None
    if calendar:
        names = service.CALENDARS[_calendar(calendar)].source_names
    q = (
        select(Capture.id, Source.name, Capture.fetched_at, Capture.http_status,
               Capture.content_type, Capture.sha256, Capture.size_bytes)
        .join(Source, Source.id == Capture.source_id)
        .order_by(Capture.id.desc())
        .limit(limit)
    )
    if names:
        q = q.where(Source.name.in_(names))
    with db.session() as s:
        rows = s.execute(q).all()
        used = _applied(s, [r.id for r in rows])
    return {
        "captures": [
            {
                "id": r.id, "source": r.name, "fetched_at": r.fetched_at.isoformat(),
                "http_status": r.http_status, "content_type": r.content_type,
                "sha256": r.sha256, "size_bytes": r.size_bytes, "applied": r.id in used,
            }
            for r in rows
        ]
    }


def _applied(s, ids: list[int]) -> set[int]:
    """Captures some calendar row came from: their parse was applied.

    A capture newer than its source's applied one, and not applied itself,
    usually failed to parse (the job answered 422). An older capture can also
    read false once a later one has replaced every row it wrote.
    """
    if not ids:
        return set()
    years = s.scalars(select(CalendarYear.capture_id).where(CalendarYear.capture_id.in_(ids)))
    days = s.scalars(select(CalendarDay.capture_id).where(CalendarDay.capture_id.in_(ids)))
    return set(years) | set(days)


def _load(s, capture_id: int) -> tuple[Capture, str]:
    row = s.execute(
        select(Capture, Source.name).join(Source, Source.id == Capture.source_id).where(Capture.id == capture_id)
    ).first()
    if row is None:
        raise HTTPException(404, f"no capture {capture_id}")
    return row[0], row[1]


@router.get("/captures/{capture_id}", dependencies=[Depends(require_read_token)])
def get_capture(capture_id: int) -> Response:
    """One capture's body, byte for byte as fetched, as a download."""
    with db.session() as s:
        cap, source = _load(s, capture_id)
        body, ctype, sha = cap.body, cap.content_type, cap.sha256
    return Response(
        content=body,
        media_type=ctype or "application/octet-stream",
        headers={
            # A download, never rendered: it's someone else's page.
            "Content-Disposition": f'attachment; filename="{source}-{capture_id}"',
            "X-Content-Type-Options": "nosniff",
            "X-Capture-Source": source,
            "X-Capture-Sha256": sha,
        },
    )


@router.get("/captures/{capture_id}/text", dependencies=[Depends(require_read_token)])
def capture_text(
    capture_id: int,
    contains: str = "",
    context: int = Query(0, ge=0, le=10),
    limit: int = Query(40, ge=1, le=400),
) -> dict:
    """An HTML capture's visible text, one line per block element, numbered.

    `contains` keeps matching lines (case-insensitive) plus `context` lines
    either side. For reading what a parser sees without downloading the page.
    """
    with db.session() as s:
        cap, source = _load(s, capture_id)
        body, ctype, fetched = cap.body, cap.content_type or "", cap.fetched_at
    if "html" not in ctype.lower() and not body.lstrip()[:15].lower().startswith((b"<!doctype", b"<html")):
        raise HTTPException(415, f"capture {capture_id} is {ctype or 'not HTML'}; only HTML has a text view")
    all_lines = text.lines(body.decode("utf-8", errors="replace"))
    if contains:
        hits = [i for i, ln in enumerate(all_lines) if contains.lower() in ln.lower()]
        keep = sorted({j for i in hits for j in range(max(0, i - context), min(len(all_lines), i + context + 1))})
    else:
        hits, keep = [], list(range(len(all_lines)))
    return {
        "capture_id": capture_id, "source": source, "fetched_at": fetched.isoformat(),
        "lines_total": len(all_lines), "matches": len(hits) if contains else None,
        "truncated": len(keep) > limit,
        "lines": [{"n": i + 1, "text": all_lines[i]} for i in keep[:limit]],
    }
