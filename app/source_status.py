"""Every source mkt-data captures, with how its captures are going (docs/phase-3.md, step 8).

For mkt-ui's Sources screen, through gRPC `SourceStatus` and mkt-api: the
calendar pages (phase 1), the CMT yields (phase 2) and the Treasury
securities sources (phase 3) in one list, each with its latest fetch and
parse, errors in the last week, what's stored and the periods it covers. The
same facts as the /metrics source gauges and GET /jobs/checks, read without
ever loading a capture's body.
"""

from dataclasses import dataclass
from datetime import UTC, datetime, timedelta

from sqlalchemy import and_, exists, func, not_, or_, select
from sqlalchemy.orm import Session, aliased

from app.calendars import service
from app.calendars.service import SourceSpec
from app.futures import sources as futures
from app.models import Capture, Source, SourceCheck
from app.rates import sources as rates
from app.securities import sources as securities

# How each group of sources is fetched: the DAG, when it runs, and how long without a successful fetch is late.
# tests/test_source_status.py checks every DAG id and schedule here against dags/, so this can't drift from them.
# A weekday DAG: Thursday evening to the next Tuesday evening covers a weekend with a closed day on each side (FedInvest
# isn't fetched on SIFMA-US holidays), so one missed weekday is caught within a day or two, never on a long weekend.
WEEKDAYS_LATE_HOURS = 120
WEEKLY_LATE_HOURS = 192  # a weekly DAG: 8 days (the capture-stale alert's threshold)


@dataclass(frozen=True)
class Schedule:
    dag: str
    when: str  # in words
    cron: str  # as in the DAG file, for the drift test
    late_after_hours: int


CALENDAR_SCHEDULES = {
    "FED": Schedule("mkt_data__fed_calendar", "Mondays 11:17 UTC", "17 11 * * 1", WEEKLY_LATE_HOURS),
    "SIFMA-US": Schedule("mkt_data__sifma_calendar", "Mondays 11:23 UTC", "23 11 * * 1", WEEKLY_LATE_HOURS),
    "NYSE": Schedule("mkt_data__nyse_calendar", "Mondays 11:29 UTC", "29 11 * * 1", WEEKLY_LATE_HOURS),
    "CME-IR": Schedule("mkt_data__cme_calendars", "Mondays 11:35 UTC", "35 11 * * 1", WEEKLY_LATE_HOURS),
    "CME-FX": Schedule("mkt_data__cme_calendars", "Mondays 11:35 UTC", "35 11 * * 1", WEEKLY_LATE_HOURS),
    "GB": Schedule("mkt_data__fx_calendars", "Mondays 11:41 UTC", "41 11 * * 1", WEEKLY_LATE_HOURS),
    "TARGET": Schedule("mkt_data__fx_calendars", "Mondays 11:41 UTC", "41 11 * * 1", WEEKLY_LATE_HOURS),
    "CA": Schedule("mkt_data__fx_calendars", "Mondays 11:41 UTC", "41 11 * * 1", WEEKLY_LATE_HOURS),
    "CH": Schedule("mkt_data__fx_calendars", "Mondays 11:41 UTC", "41 11 * * 1", WEEKLY_LATE_HOURS),
    "AU": Schedule("mkt_data__fx_calendars", "Mondays 11:41 UTC", "41 11 * * 1", WEEKLY_LATE_HOURS),
    "NZ": Schedule("mkt_data__fx_calendars", "Mondays 11:41 UTC", "41 11 * * 1", WEEKLY_LATE_HOURS),
    "SE": Schedule("mkt_data__fx_calendars", "Mondays 11:41 UTC", "41 11 * * 1", WEEKLY_LATE_HOURS),
    "NO": Schedule("mkt_data__fx_calendars", "Mondays 11:41 UTC", "41 11 * * 1", WEEKLY_LATE_HOURS),
    "DK": Schedule("mkt_data__fx_calendars", "Mondays 11:41 UTC", "41 11 * * 1", WEEKLY_LATE_HOURS),
    "MX": Schedule("mkt_data__fx_calendars", "Mondays 11:41 UTC", "41 11 * * 1", WEEKLY_LATE_HOURS),
    "BR": Schedule("mkt_data__fx_calendars", "Mondays 11:41 UTC", "41 11 * * 1", WEEKLY_LATE_HOURS),
    "ZA": Schedule("mkt_data__fx_calendars", "Mondays 11:41 UTC", "41 11 * * 1", WEEKLY_LATE_HOURS),
    "PL": Schedule("mkt_data__fx_calendars", "Mondays 11:41 UTC", "41 11 * * 1", WEEKLY_LATE_HOURS),
    "CZ": Schedule("mkt_data__fx_calendars", "Mondays 11:41 UTC", "41 11 * * 1", WEEKLY_LATE_HOURS),
    "HU": Schedule("mkt_data__fx_calendars", "Mondays 11:41 UTC", "41 11 * * 1", WEEKLY_LATE_HOURS),
    "JP": Schedule("mkt_data__fx_calendars", "Mondays 11:41 UTC", "41 11 * * 1", WEEKLY_LATE_HOURS),
}
SOURCE_SCHEDULES = {
    "UST-PAR": Schedule("mkt_data__ust_par", "Weekdays 6:30 p.m. New York", "30 18 * * 1-5", WEEKDAYS_LATE_HOURS),
    "H15-TCM": Schedule("mkt_data__h15_tcm", "Weekdays 4:30 p.m. New York", "30 16 * * 1-5", WEEKDAYS_LATE_HOURS),
}
SECURITIES_SCHEDULE = Schedule("mkt_data__treasury_securities_capture", "Weekdays 7:15 p.m. New York",
                               "15 19 * * 1-5", WEEKDAYS_LATE_HOURS)
FUTURES_SCHEDULE = Schedule("mkt_data__futures_sources_capture", "Weekdays 7:45 p.m. New York",
                            "45 19 * * 1-5", WEEKDAYS_LATE_HOURS)
# Phase 4's DAG re-fetches the latest CFTC report every weekday, so the weekly report is held to the weekday limit.
GROUP_SCHEDULES = {"securities": SECURITIES_SCHEDULE, "futures": FUTURES_SCHEDULE}


def schedule_for(e: "Entry") -> Schedule:
    if e.group == "calendars":
        return CALENDAR_SCHEDULES[e.calendar]
    return SOURCE_SCHEDULES.get(e.name) or GROUP_SCHEDULES[e.group]


def pulls_for(e: "Entry") -> str:
    """What's taken from the source and who reads it: the spec's text, or for a calendar source, its role."""
    if e.spec.pulls:
        return e.spec.pulls
    cal = service.CALENDARS[e.calendar]
    names = [s.name for s in cal.sources]
    rank = names.index(e.name) + 1 if e.name in names else 0
    what = {"published": "The closed days and early closes it publishes",
            "rules": "The holiday rules (with cited exceptions) run over the years it covers",
            "projected": "The holiday rules run forward to 2100"}.get(e.kind, "Its dates")
    role = ("fills only years no other source covers" if e.kind == "projected"
            else f"precedence {rank} of {len(names)}: a higher source decides any date it lists")
    return f"{what}, for {e.calendar}. calendar-svc reads them into the golden {e.calendar} calendar ({role})."


FETCHED = ("new", "unchanged")
RECENT_DAYS = 7
DEFAULT_CHECKS = 50
MAX_CHECKS = 500


class UnknownSource(LookupError):
    pass


@dataclass(frozen=True)
class Entry:
    name: str
    group: str  # calendars | rates | securities | futures
    calendar: str
    kind: str  # published | rules | projected
    period_kind: str  # day | month | year; "" for a one-page source
    spec: SourceSpec
    first_period: str = ""  # the earliest period the source serves; "" for a one-page source


def catalog() -> list[Entry]:
    """Every source, in the order the platform grew: calendars, rates, securities, then futures (phase 4)."""
    out: dict[str, Entry] = {}
    for cal in service.CALENDARS.values():
        for src in cal.sources:
            out.setdefault(src.name, Entry(src.name, "calendars", cal.name, service.source_kind(src), "", src))
    for name, src in rates.SOURCES.items():
        out.setdefault(name, Entry(name, "rates", src.calendar, "published", "month", src.spec, src.first_period))
    for name, src in securities.SOURCES.items():
        out.setdefault(name, Entry(name, "securities", src.calendar, "published", src.kind, src.spec,
                                   src.first_period))
    for name, src in futures.SOURCES.items():
        out.setdefault(name, Entry(name, "futures", src.calendar, "published", src.kind, src.spec,
                                   src.first_period))
    return list(out.values())


def is_error(c):
    """A check that failed: a fetch error (but not a period that isn't published yet, which is expected) or a
    parse error."""
    return or_(and_(c.outcome == "error", not_(func.coalesce(c.detail, "").contains("NOT_PUBLISHED"))),
               c.parse_outcome == "error")


def unfixed_error(c):
    """A failed check that no later check has fixed: no later check of the same source and period (both without a
    period, for a source fetched whole) worked. A backfill's failure that a re-run fetched, or a parse error a
    later reparse got through, doesn't count (Bill, 2026-10-09: show only errors that haven't been fixed)."""
    later = aliased(SourceCheck)
    same_period = or_(later.period == c.period, and_(later.period.is_(None), c.period.is_(None)))
    fixed = exists().where(later.source_id == c.source_id, same_period, later.id > c.id, not_(is_error(later)))
    return and_(is_error(c), not_(fixed))


def _aware(t: datetime) -> datetime:
    return t if t.tzinfo else t.replace(tzinfo=UTC)


def _iso(t) -> str:
    if t is None:
        return ""
    return (t if t.tzinfo else t.replace(tzinfo=UTC)).isoformat()


def _states(s: Session, entries: list[Entry], now: datetime) -> list[dict]:
    rows = {n: (i, url, desc) for i, n, url, desc in s.execute(
        select(Source.id, Source.name, Source.url, Source.description).where(
            Source.name.in_([e.name for e in entries])))}
    ids = [i for i, _, _ in rows.values()]
    stored = {sid: r for sid, *r in s.execute(
        select(Capture.source_id, func.count(), func.coalesce(func.sum(Capture.size_bytes), 0), func.max(Capture.id),
               func.max(Capture.fetched_at), func.count(Capture.period.distinct()), func.min(Capture.period),
               func.max(Capture.period))
        .where(Capture.source_id.in_(ids)).group_by(Capture.source_id))}
    last_ok = dict(s.execute(
        select(SourceCheck.source_id, func.max(SourceCheck.checked_at))
        .where(SourceCheck.source_id.in_(ids), SourceCheck.outcome.in_(FETCHED)).group_by(SourceCheck.source_id)).all())
    newest = select(func.max(SourceCheck.id)).where(SourceCheck.source_id.in_(ids)).group_by(SourceCheck.source_id)
    last = {c.source_id: c for c in s.scalars(select(SourceCheck).where(SourceCheck.id.in_(newest)))}
    since = now - timedelta(days=RECENT_DAYS)
    checks_n = dict(s.execute(
        select(SourceCheck.source_id, func.count())
        .where(SourceCheck.source_id.in_(ids), SourceCheck.checked_at >= since).group_by(SourceCheck.source_id)).all())
    # A period before the source's first can't be fetched, so its old failure is moot (FRB-H10's probe asked for
    # 2000-2005 before its first period was found to be 2006-01).
    first = {rows[e.name][0]: e.first_period for e in entries if e.name in rows and e.first_period}
    unfixed: dict[int, int] = {}
    for sid, period in s.execute(
            select(SourceCheck.source_id, SourceCheck.period)
            .where(SourceCheck.source_id.in_(ids), SourceCheck.checked_at >= since, unfixed_error(SourceCheck))):
        if period and sid in first and period < first[sid]:
            continue
        unfixed[sid] = unfixed.get(sid, 0) + 1
    recent = {sid: (n, unfixed.get(sid, 0)) for sid, n in checks_n.items()}
    out = []
    for e in entries:
        sched = schedule_for(e)
        sid, url, desc = rows.get(e.name, (None, e.spec.url, e.spec.description))
        n, size, cap_id, cap_at, periods, first, last_p = stored.get(sid, (0, 0, None, None, 0, None, None))
        check = last.get(sid)
        failed = check is not None and (check.outcome == "error" or check.parse_outcome == "error")
        checks, errors = recent.get(sid, (0, 0))
        out.append({
            "name": e.name, "group": e.group, "calendar": e.calendar, "kind": e.kind, "period_kind": e.period_kind,
            "url": url or e.spec.url, "description": desc or e.spec.description, "parsed": e.spec.parse is not None,
            "captures": n, "capture_bytes": int(size), "latest_capture_id": cap_id or 0,
            "latest_capture_at": _iso(cap_at), "last_success_at": _iso(last_ok.get(sid)),
            "last_check_at": _iso(check.checked_at) if check else "", "last_outcome": check.outcome if check else "",
            "last_parse_outcome": (check.parse_outcome or "") if check else "",
            "last_error": ((check.detail if check.outcome == "error" else check.parse_detail) or "")[:500]
            if failed else "",
            "checks_7d": checks, "errors_7d": errors,
            "periods": periods if e.period_kind else 0, "first_period": (first or "") if e.period_kind else "",
            "last_period": (last_p or "") if e.period_kind else "",
            "pulls": pulls_for(e), "dag": sched.dag, "schedule": sched.when, "late_after_hours": sched.late_after_hours,
            "late": sid in last_ok and now - _aware(last_ok[sid]) > timedelta(hours=sched.late_after_hours),
        })
    return out


def list_sources(s: Session, now: datetime | None = None) -> list[dict]:
    return _states(s, catalog(), now or datetime.now(UTC))


def get_source(s: Session, name: str, checks: int = DEFAULT_CHECKS, now: datetime | None = None) -> dict:
    entry = next((e for e in catalog() if e.name == name.upper()), None)
    if entry is None:
        raise UnknownSource(f"no source {name!r}")
    state = _states(s, [entry], now or datetime.now(UTC))[0]
    sid = s.scalar(select(Source.id).where(Source.name == entry.name))
    if sid is None:
        return {"source": state, "checks": [], "years": []}
    limit = min(max(checks or DEFAULT_CHECKS, 1), MAX_CHECKS)
    rows = s.scalars(select(SourceCheck).where(SourceCheck.source_id == sid)
                     .order_by(SourceCheck.id.desc()).limit(limit)).all()
    years = []
    if entry.period_kind:
        year = func.substr(Capture.period, 1, 4)
        years = [{"year": y, "periods": p, "captures": n, "capture_bytes": int(b)} for y, p, n, b in s.execute(
            select(year, func.count(Capture.period.distinct()), func.count(), func.coalesce(func.sum(Capture.size_bytes), 0))
            .where(Capture.source_id == sid, Capture.period.is_not(None)).group_by(year).order_by(year))]
    return {
        "source": state,
        "checks": [{"id": c.id, "checked_at": _iso(c.checked_at), "outcome": c.outcome, "capture_id": c.capture_id or 0,
                    "period": c.period or "", "detail": c.detail or "", "parse_outcome": c.parse_outcome or "",
                    "parse_detail": c.parse_detail or ""} for c in rows],
        "years": years,
    }


def capture_text(s: Session, capture_id: int, contains: str = "", context: int = 0, offset: int = 0,
                 limit: int = 200) -> dict:
    """A capture's text lines (app/capture_text.py), a page at a time. UnknownCapture; capture_text.NoTextView."""
    from app import capture_text as text_view

    row = s.execute(select(Capture.body, Capture.content_type, Capture.fetched_at, Capture.period, Source.name)
                    .join(Source, Source.id == Capture.source_id).where(Capture.id == capture_id)).first()
    if row is None:
        raise UnknownCapture(f"no capture {capture_id}")
    body, ctype, fetched, period, source = row
    view, lines = text_view.lines(capture_id, body, ctype or "")
    keep, matches = text_view.select_lines(lines, contains, min(max(context, 0), 10))
    start = max(offset, 0)
    shown = keep[start:start + min(limit or 200, 1000)]
    return {"capture_id": capture_id, "source": source, "period": period or "", "fetched_at": _iso(fetched),
            "view": view, "lines_total": len(lines), "matches": matches if matches is not None else -1,
            "offset": start, "shown_of": len(keep), "lines": [{"n": i + 1, "text": lines[i]} for i in shown]}


class UnknownCapture(LookupError):
    pass
