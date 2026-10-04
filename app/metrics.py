"""Prometheus metrics: the calendar sources' capture health (docs/phase-1.md step 7).

GET /metrics, in Prometheus's text format, computed from the database on
each scrape. Prometheus scrapes it on the home-platform network as
mkt-data:8000; no auth, like the other scrape targets, and nothing in it is
sensitive (counts and timestamps). Labels use readable names
(calendar="SIFMA-US", source="SIFMA-US-ARCHIVE", kind=published/rules/projected).

The platform's Grafana alert rules (nyc_pa_aws_gitops) use:
- mkt_data_source_last_success_timestamp_seconds: a capture is stale;
- mkt_data_source_parse_ok: the latest parse of a source failed.
The calendars' own gauges (coverage, gaps, upcoming closes, next year
published) come from calendar-svc since phase 2, step A5.
"""

from datetime import UTC, datetime

from fastapi import APIRouter, Response
from sqlalchemy import func, select
from sqlalchemy.exc import SQLAlchemyError

from app import db
from app.calendars import service
from app.models import Capture, Source, SourceCheck

router = APIRouter()

FETCHED = ("new", "unchanged")


class _Out:
    def __init__(self):
        self.lines: list[str] = []

    def metric(self, name: str, kind: str, help_: str, samples: list[tuple[dict, float]]) -> None:
        self.lines += [f"# HELP {name} {help_}", f"# TYPE {name} {kind}"]
        for labels, value in samples:
            body = ",".join(f'{k}="{_escape(v)}"' for k, v in labels.items())
            self.lines.append(f"{name}{{{body}}} {_num(value)}" if body else f"{name} {_num(value)}")

    def text(self) -> str:
        return "\n".join(self.lines) + "\n"


def _escape(v) -> str:
    return str(v).replace("\\", "\\\\").replace('"', '\\"').replace("\n", "\\n")


def _epoch(t: datetime) -> float:
    # Postgres returns aware timestamps; SQLite (tests) returns naive UTC ones.
    return (t if t.tzinfo else t.replace(tzinfo=UTC)).timestamp()


def _num(v: float) -> str:
    return str(int(v)) if float(v).is_integer() else repr(float(v))


@router.get("/metrics", include_in_schema=False)
def metrics() -> Response:
    out = _Out()
    try:
        with db.session() as s:
            _collect(s, out)
        up = 1
    except (SQLAlchemyError, db.DatabaseNotConfigured):
        up = 0  # no database configured, or it's unreachable
    out.metric("mkt_data_db_up", "gauge", "1 if the metrics could be read from the database.", [({}, up)])
    return Response(out.text(), media_type="text/plain; version=0.0.4; charset=utf-8")


def _collect(s, out: _Out) -> None:
    specs = service.CALENDARS
    source_ids = {n: i for n, i in s.execute(select(Source.name, Source.id))}
    cal_of = {src.name: cal.name for cal in specs.values() for src in cal.sources}
    kind_of = {src.name: service.source_kind(src) for cal in specs.values() for src in cal.sources}

    # Per source: last successful fetch, latest parse outcome, captures and bytes.
    last_ok = dict(s.execute(
        select(SourceCheck.source_id, func.max(SourceCheck.checked_at))
        .where(SourceCheck.outcome.in_(FETCHED)).group_by(SourceCheck.source_id)
    ).all())
    latest_parse = {}
    for sid, outcome in s.execute(
        select(SourceCheck.source_id, SourceCheck.parse_outcome)
        .where(SourceCheck.parse_outcome.is_not(None)).order_by(SourceCheck.id)
    ):
        latest_parse[sid] = outcome  # ordered by id, so the last one wins
    stored = {sid: (n, b) for sid, n, b in s.execute(
        select(Capture.source_id, func.count(), func.coalesce(func.sum(Capture.size_bytes), 0)).group_by(Capture.source_id)
    )}

    success, parse_ok, captures, size = [], [], [], []
    for name, cal in cal_of.items():
        sid = source_ids.get(name)
        labels = {"calendar": cal, "source": name, "kind": kind_of[name]}
        if sid is None:
            continue  # not captured yet
        if sid in last_ok:
            success.append((labels, _epoch(last_ok[sid])))
        if sid in latest_parse:
            parse_ok.append((labels, 1 if latest_parse[sid] == "ok" else 0))
        n, b = stored.get(sid, (0, 0))
        captures.append((labels, n))
        size.append((labels, b))
    out.metric("mkt_data_source_last_success_timestamp_seconds", "gauge",
               "When the source was last fetched (or read) successfully.", success)
    out.metric("mkt_data_source_parse_ok", "gauge", "1 if the source's latest parse worked, 0 if it failed.", parse_ok)
    out.metric("mkt_data_source_captures", "gauge", "Raw captures stored for the source.", captures)
    out.metric("mkt_data_source_capture_bytes", "gauge", "Raw bytes stored for the source.", size)
