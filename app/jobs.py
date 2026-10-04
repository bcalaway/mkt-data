"""Job API for Airflow (ADR-0031 in nyc_pa_aws_gitops).

Airflow's DAGs call these over the home-platform network; the work runs
here, in this app's own container. Every endpoint:

- requires `Authorization: Bearer <AIRFLOW_TOKEN>` (other apps and previews
  share the network),
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
from app.calendars import service
from app.calendars.parsed import ParseError
from app.config import settings
from app.models import Capture, Source

router = APIRouter(prefix="/jobs")


def require_token(authorization: str | None = Header(default=None)) -> None:
    if not settings.airflow_token:
        raise HTTPException(503, "job API disabled: AIRFLOW_TOKEN isn't set")
    given = (authorization or "").removeprefix("Bearer ").strip()
    if not hmac.compare_digest(given.encode(), settings.airflow_token.encode()):
        raise HTTPException(401, "bad or missing job token")


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


@router.get("/calendars/{name}/business-day", dependencies=[Depends(require_token)])
def business_day(name: str, on: date) -> dict:
    """Is `on` a business day for this calendar? For DAGs' short-circuit first task."""
    key = _calendar(name)
    try:
        with db.session() as s:
            return service.business_day(s, key, on)
    except service.NotCovered as e:
        raise HTTPException(409, str(e)) from None


# Raw captures, read-only: for turning a real capture into a test fixture,
# or checking what a parser saw. Same token as the jobs above.


@router.get("/captures", dependencies=[Depends(require_token)])
def list_captures(
    source: str | None = None, calendar: str | None = None, limit: int = Query(20, ge=1, le=200)
) -> dict:
    """Newest captures first, metadata only. Filter by source or calendar name."""
    if source and calendar:
        raise HTTPException(400, "give source or calendar, not both")
    if calendar:
        source = service.CALENDARS[_calendar(calendar)].source_name
    q = (
        select(Capture.id, Source.name, Capture.fetched_at, Capture.http_status,
               Capture.content_type, Capture.sha256, Capture.size_bytes)
        .join(Source, Source.id == Capture.source_id)
        .order_by(Capture.id.desc())
        .limit(limit)
    )
    if source:
        q = q.where(Source.name == source.upper())
    with db.session() as s:
        rows = s.execute(q).all()
    return {
        "captures": [
            {
                "id": r.id, "source": r.name, "fetched_at": r.fetched_at.isoformat(),
                "http_status": r.http_status, "content_type": r.content_type,
                "sha256": r.sha256, "size_bytes": r.size_bytes,
            }
            for r in rows
        ]
    }


@router.get("/captures/{capture_id}", dependencies=[Depends(require_token)])
def get_capture(capture_id: int) -> Response:
    """One capture's body, byte for byte as fetched, as a download."""
    with db.session() as s:
        row = s.execute(
            select(Capture, Source.name).join(Source, Source.id == Capture.source_id).where(Capture.id == capture_id)
        ).first()
        if row is None:
            raise HTTPException(404, f"no capture {capture_id}")
        cap, source = row
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
