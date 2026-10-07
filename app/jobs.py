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
content can't be parsed (the raw capture is kept), 409 when there's nothing
to reparse. The business-day answer moved to calendar-svc (phase 2, A5).
"""

import hmac
import json

from fastapi import APIRouter, Depends, Header, HTTPException, Query, Response
from sqlalchemy import select

from app import db
from app.calendars import rsc, service, text
from app.calendars.parsed import ParseError
from app.config import settings
from app.models import Capture, Observation, Record, Source, SourceCheck, SourceDay, SourceYear
from app.rates import sources as rates
from app.securities import sources as securities

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


@router.post("/calendars/{name}/near-raw/rebuild", dependencies=[Depends(require_token)])
def rebuild_near_raw(name: str) -> dict:
    """Rebuild the calendar's sources' near-raw rows by replaying every capture. No fetch.

    For filling near-raw from captures taken before it existed, or applying a
    parser fix to a source's whole history. A capture that fails to parse is
    skipped and listed under its source's `parse_failed`.
    """
    key = _calendar(name)
    with db.session() as s:
        return service.run_near_raw_rebuild(s, key)


@router.post("/rates/{source}/capture", dependencies=[Depends(require_token)])
def capture_rates(source: str, period: str | None = None) -> dict:
    """Fetch one month (default: the current one, in New York) of a CMT source; keep it raw if new,
    and record its observations.

    `source` is UST-PAR or H15-TCM (app/rates/sources.py), `period` YYYY-MM.
    """
    key = source.upper()
    if key not in rates.SOURCES:
        raise HTTPException(404, f"unknown rate source {source!r}; known: {sorted(rates.SOURCES)}")
    try:
        with db.session() as s:
            return rates.run_capture(s, key, period or rates.current_period())
    except rates.BadPeriod as e:
        raise HTTPException(400, str(e)) from None
    except service.SourceFetchError as e:
        raise HTTPException(502, f"fetch failed: {e}") from None
    except ParseError as e:
        raise HTTPException(422, f"parse failed (raw capture kept): {e}") from None


@router.post("/rates/{source}/rebuild", dependencies=[Depends(require_token)])
def rebuild_rates(source: str) -> dict:
    """Rebuild a CMT source's observations by replaying every stored capture. No fetch."""
    key = source.upper()
    if key not in rates.SOURCES:
        raise HTTPException(404, f"unknown rate source {source!r}; known: {sorted(rates.SOURCES)}")
    with db.session() as s:
        return rates.run_rebuild(s, key)


@router.post("/securities/{source}/capture", dependencies=[Depends(require_token)])
def capture_securities(source: str, period: str | None = None) -> dict:
    """Fetch one period of a Treasury securities source, keep it raw if new, and apply its parse (phase 3).

    `source` is TD-SECURITIES, TD-PRICES, FD-AUCTIONS, FD-MSPD-STRIPS or BLS-CPI
    (app/securities/sources.py). `period` is the source's kind (a month
    YYYY-MM, a day YYYY-MM-DD or a year YYYY); default: the current one, in New York.
    """
    key = source.upper()
    if key not in securities.SOURCES:
        raise HTTPException(404, f"unknown securities source {source!r}; known: {sorted(securities.SOURCES)}")
    src = securities.SOURCES[key]
    try:
        with db.session() as s:
            return securities.run_capture(s, key, period or securities.current_period(src.kind))
    except securities.BadPeriod as e:
        raise HTTPException(400, str(e)) from None
    except service.SourceFetchError as e:
        raise HTTPException(502, f"fetch failed: {e}") from None
    except ParseError as e:
        raise HTTPException(422, f"parse failed (raw capture kept): {e}") from None


@router.post("/securities/{source}/rebuild", dependencies=[Depends(require_token)])
def rebuild_securities(source: str) -> dict:
    """Rebuild a Treasury securities source's near-raw rows (records or observations) from every capture. No fetch."""
    key = source.upper()
    if key not in securities.SOURCES:
        raise HTTPException(404, f"unknown securities source {source!r}; known: {sorted(securities.SOURCES)}")
    with db.session() as s:
        return securities.run_rebuild(s, key)


@router.post("/securities/compare", dependencies=[Depends(require_token)])
def compare_securities() -> dict:
    """Cross-check TreasuryDirect's auction records against Fiscal Data's; kept for the metrics (docs/phase-3.md, step 5)."""
    from app.securities import compare

    with db.session() as s:
        return compare.run(s)


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
               Capture.content_type, Capture.sha256, Capture.size_bytes, Capture.period)
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
                "sha256": r.sha256, "size_bytes": r.size_bytes, "period": r.period, "applied": r.id in used,
                # False for a source with no parser yet: kept raw, never applied.
                "parsed": _has_parser(r.name),
            }
            for r in rows
        ]
    }


@router.get("/checks", dependencies=[Depends(require_read_token)])
def list_checks(
    source: str | None = None, calendar: str | None = None, limit: int = Query(20, ge=1, le=200)
) -> dict:
    """Newest fetch attempts and reparses first: what each capture job did per source.

    outcome is new / unchanged / error (fetch) or reparse; parse_outcome is
    ok / error (empty for a fetch error or a source with no parser); detail
    and parse_detail hold the messages (a fetch error, "markup changed,
    visible text identical", a parse error).
    """
    if source and calendar:
        raise HTTPException(400, "give source or calendar, not both")
    names = [source.upper()] if source else None
    if calendar:
        names = service.CALENDARS[_calendar(calendar)].source_names
    q = (
        select(SourceCheck.id, Source.name, SourceCheck.checked_at, SourceCheck.outcome, SourceCheck.capture_id,
               SourceCheck.detail, SourceCheck.parse_outcome, SourceCheck.parse_detail, SourceCheck.period)
        .join(Source, Source.id == SourceCheck.source_id)
        .order_by(SourceCheck.id.desc())
        .limit(limit)
    )
    if names:
        q = q.where(Source.name.in_(names))
    with db.session() as s:
        rows = s.execute(q).all()
    return {
        "checks": [
            {
                "id": r.id, "source": r.name, "checked_at": r.checked_at.isoformat(), "outcome": r.outcome,
                "capture_id": r.capture_id, "detail": r.detail,
                "parse_outcome": r.parse_outcome, "parse_detail": r.parse_detail, "period": r.period,
            }
            for r in rows
        ]
    }


def _has_parser(source: str) -> bool:
    spec = service.SOURCES.get(source)
    for registry in (rates.SOURCES, securities.SOURCES):
        if spec is None and source in registry:
            spec = registry[source].spec
    return spec is not None and spec.parse is not None


def _applied(s, ids: list[int]) -> set[int]:
    """Captures some near-raw row came from: their parse was recorded.

    A capture newer than its source's applied one, and not applied itself,
    usually failed to parse (the job answered 422), or changed nothing a
    previous capture hadn't already said.
    """
    if not ids:
        return set()
    years = s.scalars(select(SourceYear.capture_id).where(SourceYear.capture_id.in_(ids)))
    days = s.scalars(select(SourceDay.capture_id).where(SourceDay.capture_id.in_(ids)))
    obs = s.scalars(select(Observation.capture_id).where(Observation.capture_id.in_(ids)).distinct())
    recs = s.scalars(select(Record.capture_id).where(Record.capture_id.in_(ids)).distinct())
    return set(years) | set(days) | set(obs) | set(recs)


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
    embedded: bool = False,
) -> dict:
    """A capture's text, numbered: an HTML page's visible text (one line per block element), JSON
    pretty-printed one value per line, and anything else textual (CSV, XML) line by line.

    `contains` keeps matching lines (case-insensitive) plus `context` lines
    either side. For reading what a parser sees without downloading the page.
    `embedded=true` shows the text of a Next.js page's embedded React data
    instead (rsc.py): what SIFMA's parser reads, hidden year tabs included.
    """
    with db.session() as s:
        cap, source = _load(s, capture_id)
        body, ctype, fetched = cap.body, cap.content_type or "", cap.fetched_at
    view, all_lines = _text_lines(capture_id, body, ctype, embedded)
    if contains:
        hits = [i for i, ln in enumerate(all_lines) if contains.lower() in ln.lower()]
        keep = sorted({j for i in hits for j in range(max(0, i - context), min(len(all_lines), i + context + 1))})
    else:
        hits, keep = [], list(range(len(all_lines)))
    return {
        "capture_id": capture_id, "source": source, "fetched_at": fetched.isoformat(),
        "view": view, "lines_total": len(all_lines), "matches": len(hits) if contains else None,
        "truncated": len(keep) > limit,
        "lines": [{"n": i + 1, "text": all_lines[i]} for i in keep[:limit]],
    }


def _text_lines(capture_id: int, body: bytes, ctype: str, embedded: bool) -> tuple[str, list[str]]:
    is_html = "html" in ctype.lower() or body.lstrip()[:15].lower().startswith((b"<!doctype", b"<html"))
    if is_html:
        html = body.decode("utf-8", errors="replace")
        lines = rsc.lines(html) if embedded else text.lines(html)
        if embedded and not lines:
            raise HTTPException(404, f"capture {capture_id} has no embedded React data; use the default view")
        return ("embedded" if embedded else "visible"), lines
    if embedded:
        raise HTTPException(415, f"capture {capture_id} is {ctype or 'not HTML'}; only HTML has embedded data")
    binary_type = any(t in ctype.lower() for t in ("pdf", "octet-stream", "zip", "image/", "excel", "spreadsheet"))
    if binary_type or body.startswith(b"%PDF") or b"\x00" in body[:4096]:
        raise HTTPException(415, f"capture {capture_id} is {ctype or 'binary'}; no text view")
    raw = body.decode("utf-8", errors="replace")
    try:
        doc = json.loads(raw)
    except json.JSONDecodeError:
        return "text", raw.splitlines()
    return "json", json.dumps(doc, indent=1, ensure_ascii=False).splitlines()
