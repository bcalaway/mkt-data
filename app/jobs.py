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

from fastapi import APIRouter, Depends, Header, HTTPException

from app import db
from app.calendars import service
from app.calendars.parsed import ParseError
from app.config import settings

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
