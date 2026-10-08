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

from app import db, source_status
from app.calendars import service
from app.futures import sources as futures
from app.models import Capture, Observation, RecordComparison, Source, SourceCheck
from app.rates import sources as rates
from app.securities import sources as securities

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


def _day(d) -> float:
    return datetime(d.year, d.month, d.day, tzinfo=UTC).timestamp()


def _collect(s, out: _Out) -> None:
    specs = service.CALENDARS
    source_ids = {n: i for n, i in s.execute(select(Source.name, Source.id))}
    cal_of = {src.name: cal.name for cal in specs.values() for src in cal.sources}
    kind_of = {src.name: service.source_kind(src) for cal in specs.values() for src in cal.sources}
    # The CMT sources (phase 2, Part B), labelled with their publication calendar.
    cal_of |= {name: src.calendar for name, src in rates.SOURCES.items()}
    kind_of |= {name: "published" for name in rates.SOURCES}
    # The Treasury securities sources (phase 3), likewise.
    cal_of |= {name: src.calendar for name, src in securities.SOURCES.items()}
    kind_of |= {name: "published" for name in securities.SOURCES}
    # Phase 4's fixings and positioning sources, likewise.
    cal_of |= {name: src.calendar for name, src in futures.SOURCES.items()}
    kind_of |= {name: "published" for name in futures.SOURCES}

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

    # Per source: how long without a successful fetch is late against its schedule (app/source_status.py), so the
    # capture-stale alert holds each source to its own DAG instead of one threshold for all.
    late_after = [({"calendar": cal_of[e.name], "source": e.name, "kind": kind_of[e.name]},
                    source_status.schedule_for(e).late_after_hours * 3600)
                  for e in source_status.catalog() if e.name in cal_of]
    out.metric("mkt_data_source_late_after_seconds", "gauge",
               "How long without a successful fetch the source is late, from its DAG's schedule.", late_after)

    # Per CMT source and key: the latest date with a current value, read from the source's newest month only
    # (an index range, not the whole history). A key the newest month lacks drops out.
    last_dates = []
    for name, src in sorted(rates.SOURCES.items()):
        sid = source_ids.get(name)
        if sid is None:
            continue
        newest = s.scalar(select(func.max(Observation.period)).where(Observation.source_id == sid))
        if newest is None:
            continue
        for key, as_of in s.execute(
            select(Observation.source_key, func.max(Observation.as_of))
            .where(Observation.source_id == sid, Observation.period == newest, Observation.valid_to.is_(None))
            .group_by(Observation.source_key).order_by(Observation.source_key)
        ):
            last_dates.append(({"calendar": src.calendar, "source": name, "key": key}, _day(as_of)))
    out.metric("mkt_data_observation_last_date_timestamp_seconds", "gauge",
               "Each CMT source key's latest date with a value (midnight UTC), from the source's newest month.",
               last_dates)

    # The latest cross-check of two sources' records (TreasuryDirect's auctions against Fiscal Data's).
    rows = list(s.scalars(select(RecordComparison)))
    pair = [({"left": r.left_source, "right": r.right_source}, r) for r in rows]
    out.metric("mkt_data_record_compare_timestamp_seconds", "gauge", "When the two sources' records were last compared.",
               [(lb, _epoch(r.ran_at)) for lb, r in pair])
    out.metric("mkt_data_record_compare_records", "gauge",
               "Records in the latest comparison: both (listed by both), left_only, right_only, differing "
               "(both list it and at least one field differs).",
               [(lb | {"which": w}, v) for lb, r in pair for w, v in
                (("both", r.compared), ("left_only", r.only_left), ("right_only", r.only_right),
                 ("differing", r.records_differing))])
    out.metric("mkt_data_record_compare_field", "gauge",
               "Per field in the latest comparison, records where it differs (both have values) or only one side has one.",
               [(lb | {"field": f["field"], "kind": k}, f[k]) for lb, r in pair
                for f in (r.detail or {}).get("fields", [])[:60] for k in ("different", "one_side_empty") if f.get(k)])
