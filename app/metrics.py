"""Prometheus metrics: the calendars' data quality (docs/phase-1.md, step 7).

GET /metrics, in Prometheus's text format, computed from the database on
each scrape (a handful of small queries). Prometheus scrapes it on the
home-platform network as mkt-data:8000; there's no auth, like the other
scrape targets, and nothing in it is sensitive (counts, years, timestamps).
Labels use readable names (calendar="SIFMA-US", source="SIFMA-US-ARCHIVE").

The platform's Grafana alert rules (nyc_pa_aws_gitops) use:
- mkt_data_source_last_success_timestamp_seconds: a capture is stale;
- mkt_data_source_parse_ok: the latest parse of a source failed;
- mkt_data_calendar_next_year_overdue: next year isn't published by a
  publisher yet, past its usual date (projections don't count).
The rest is for the market-data dashboard (step 8).
"""

from collections import defaultdict
from datetime import UTC, date, datetime

from fastapi import APIRouter, Response
from sqlalchemy import func, select
from sqlalchemy.exc import SQLAlchemyError

from app import db
from app.calendars import service
from app.models import Calendar, CalendarDay, CalendarYear, Capture, Source, SourceCheck

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


def _today() -> date:
    return datetime.now(UTC).date()  # a few hours' difference from Eastern doesn't matter here


@router.get("/metrics", include_in_schema=False)
def metrics() -> Response:
    out = _Out()
    try:
        with db.session() as s:
            _collect(s, out, _today())
        up = 1
    except (SQLAlchemyError, db.DatabaseNotConfigured):
        up = 0  # no database configured, or it's unreachable
    out.metric("mkt_data_db_up", "gauge", "1 if the metrics could be read from the database.", [({}, up)])
    return Response(out.text(), media_type="text/plain; version=0.0.4; charset=utf-8")


def _collect(s, out: _Out, today: date) -> None:
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

    # Per calendar: covered years by kind, current rows, next year.
    cal_ids = {n: i for n, i in s.execute(select(Calendar.name, Calendar.id))}
    year_rows = s.execute(
        select(CalendarYear.calendar_id, CalendarYear.year, Source.name)
        .join(Capture, Capture.id == CalendarYear.capture_id).join(Source, Source.id == Capture.source_id)
    ).all()
    years = defaultdict(lambda: defaultdict(list))  # calendar id -> kind -> [years]
    for cid, year, src in year_rows:
        years[cid][kind_of.get(src, "published")].append(year)
    days = defaultdict(int)
    for cid, status, n in s.execute(
        select(CalendarDay.calendar_id, CalendarDay.status, func.count())
        .where(CalendarDay.valid_to.is_(None)).group_by(CalendarDay.calendar_id, CalendarDay.status)
    ):
        days[(cid, status)] = n

    count, first, last, rows, published, overdue = [], [], [], [], [], []
    for cal in specs.values():
        cid = cal_ids.get(cal.name)
        if cid is None:
            continue
        for kind, ys in sorted(years[cid].items()):
            labels = {"calendar": cal.name, "kind": kind}
            count.append((labels, len(ys)))
            first.append((labels, min(ys)))
            last.append((labels, max(ys)))
        for status in ("closed", "early_close"):
            rows.append(({"calendar": cal.name, "status": status}, days[(cid, status)]))
        nxt = today.year + 1
        is_published = nxt in years[cid]["published"]
        due = date(today.year, *cal.next_year_due)
        published.append(({"calendar": cal.name, "year": str(nxt)}, int(is_published)))
        overdue.append(({"calendar": cal.name, "year": str(nxt)}, int(not is_published and today >= due)))
    out.metric("mkt_data_calendar_years", "gauge", "Years covered, by kind of source (published, rules, projected).", count)
    out.metric("mkt_data_calendar_first_year", "gauge", "First covered year, by kind of source.", first)
    out.metric("mkt_data_calendar_last_year", "gauge", "Last covered year, by kind of source.", last)
    out.metric("mkt_data_calendar_days", "gauge", "Current closed and early-close weekdays.", rows)
    out.metric("mkt_data_calendar_next_year_published", "gauge",
               "1 if next year is covered by a publisher (not rules or a projection).", published)
    out.metric("mkt_data_calendar_next_year_overdue", "gauge",
               "1 if next year isn't published yet and is past the calendar's usual publish date.", overdue)
