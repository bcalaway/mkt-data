"""Calendar jobs against the database: capture, parse, apply, query.

The flow for every calendar (docs/phase-1.md, step 4):

1. Fetch the source. Every attempt is a `source_check` row. New content (by
   SHA-256) becomes a `capture` row, stored byte for byte and never changed;
   the same content as last time records the check only.
2. Parse the latest capture. A parse error leaves the raw capture in place,
   so a fixed parser can re-run on it (`reparse`).
3. Apply the parse with history: within the years the source covers, new
   dates are inserted, changed dates get a new row (the old one gets
   `valid_to`), and dates no longer listed are closed off. Years the source
   stops listing are left alone.
"""

import hashlib
from collections.abc import Callable
from dataclasses import dataclass
from datetime import UTC, date, datetime

import httpx
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.calendars import fed
from app.calendars.parsed import Day, ParsedCalendar, diff
from app.models import Calendar, CalendarDay, CalendarYear, Capture, Source, SourceCheck

USER_AGENT = "mkt-data/1 (personal market data platform; bcalaway)"
FETCH_TIMEOUT_SECONDS = 60


@dataclass(frozen=True)
class CalendarSpec:
    name: str
    description: str
    timezone: str
    source_name: str
    source_url: str
    source_description: str
    parse: Callable[[bytes], ParsedCalendar]


CALENDARS: dict[str, CalendarSpec] = {
    "FED": CalendarSpec(
        name="FED",
        description="Federal Reserve Banks and Fedwire: closed weekdays",
        timezone="America/New_York",
        source_name="FED-K8",
        source_url=fed.URL,
        source_description="Federal Reserve Board, K.8 Holidays Observed (current year + 4)",
        parse=fed.parse,
    ),
}


class SourceFetchError(RuntimeError):
    pass


class NotCovered(LookupError):
    pass


def _source(s: Session, spec: CalendarSpec) -> Source:
    src = s.scalar(select(Source).where(Source.name == spec.source_name))
    if src is None:
        src = Source(name=spec.source_name, url=spec.source_url, description=spec.source_description)
        s.add(src)
        s.flush()
    elif src.url != spec.source_url or src.description != spec.source_description:
        src.url, src.description = spec.source_url, spec.source_description
    return src


def _calendar(s: Session, spec: CalendarSpec) -> Calendar:
    cal = s.scalar(select(Calendar).where(Calendar.name == spec.name))
    if cal is None:
        cal = Calendar(name=spec.name, description=spec.description, timezone=spec.timezone)
        s.add(cal)
        s.flush()
    return cal


def fetch(url: str) -> tuple[int, str | None, bytes]:
    try:
        r = httpx.get(
            url, timeout=FETCH_TIMEOUT_SECONDS, follow_redirects=True, headers={"User-Agent": USER_AGENT}
        )
    except httpx.HTTPError as e:
        raise SourceFetchError(f"{url}: {e}") from None
    if r.status_code != 200:
        raise SourceFetchError(f"{url}: HTTP {r.status_code}")
    return r.status_code, r.headers.get("content-type"), r.content


def capture(s: Session, spec: CalendarSpec, fetcher=None) -> tuple[Capture, bool]:
    """Fetch the source; store the content if it's new. Returns (latest capture, is_new)."""
    src = _source(s, spec)
    try:
        status, ctype, body = (fetcher or fetch)(src.url)
    except SourceFetchError as e:
        s.add(SourceCheck(source_id=src.id, outcome="error", detail=str(e)[:2000]))
        s.commit()
        raise
    sha = hashlib.sha256(body).hexdigest()
    last = s.scalar(
        select(Capture).where(Capture.source_id == src.id).order_by(Capture.id.desc()).limit(1)
    )
    if last is not None and last.sha256 == sha:
        s.add(SourceCheck(source_id=src.id, outcome="unchanged", capture_id=last.id))
        s.flush()
        return last, False
    cap = Capture(
        source_id=src.id, http_status=status, content_type=ctype, sha256=sha, size_bytes=len(body), body=body
    )
    s.add(cap)
    s.flush()
    s.add(SourceCheck(source_id=src.id, outcome="new", capture_id=cap.id))
    s.flush()
    return cap, True


def latest_capture(s: Session, spec: CalendarSpec) -> Capture | None:
    src = _source(s, spec)
    return s.scalar(select(Capture).where(Capture.source_id == src.id).order_by(Capture.id.desc()).limit(1))


def apply(s: Session, spec: CalendarSpec, cap: Capture, parsed: ParsedCalendar) -> dict:
    cal = _calendar(s, spec)
    now = datetime.now(UTC)
    rows = s.scalars(
        select(CalendarDay).where(CalendarDay.calendar_id == cal.id, CalendarDay.valid_to.is_(None))
    ).all()
    by_day = {r.day: r for r in rows}
    current = {r.day: Day(r.day, r.status, r.holiday, r.close_time) for r in rows}
    d = diff(current, parsed)
    for day in [x.day for x in d.changed] + list(d.removed):
        by_day[day].valid_to = now
    s.flush()  # close old versions before inserting new ones (unique current row)
    for x in d.added + d.changed:
        s.add(
            CalendarDay(
                calendar_id=cal.id, day=x.day, status=x.status, close_time=x.close_time,
                holiday=x.holiday, capture_id=cap.id, valid_from=now,
            )
        )
    known = set(s.scalars(select(CalendarYear.year).where(CalendarYear.calendar_id == cal.id)))
    new_years = [y for y in parsed.years if y not in known]
    for y in parsed.years:
        if y in known:
            s.get(CalendarYear, (cal.id, y)).capture_id = cap.id
        else:
            s.add(CalendarYear(calendar_id=cal.id, year=y, capture_id=cap.id))
    return {
        "years": list(parsed.years),
        "new_years": new_years,
        "closed_days": len(parsed.days),
        "added": len(d.added),
        "changed": [x.day.isoformat() for x in d.changed],
        "removed": [x.isoformat() for x in d.removed],
    }


def run_capture(s: Session, name: str, fetcher=None) -> dict:
    spec = CALENDARS[name]
    cap, is_new = capture(s, spec, fetcher)
    # Commit the raw capture (and its check) before parsing: a parse error
    # must never lose what was fetched.
    s.commit()
    summary = {"calendar": name, "source": spec.source_name, "capture_id": cap.id, "new_capture": is_new}
    summary |= apply(s, spec, cap, spec.parse(cap.body))
    s.commit()
    return summary


def run_reparse(s: Session, name: str) -> dict:
    spec = CALENDARS[name]
    cap = latest_capture(s, spec)
    if cap is None:
        raise NotCovered(f"{name}: nothing captured yet")
    summary = {"calendar": name, "source": spec.source_name, "capture_id": cap.id, "new_capture": False}
    summary |= apply(s, spec, cap, spec.parse(cap.body))
    s.commit()
    return summary


def business_day(s: Session, name: str, day: date) -> dict:
    spec = CALENDARS[name]
    out = {"calendar": name, "date": day.isoformat()}
    if day.weekday() >= 5:
        return out | {"business_day": False, "status": "weekend"}
    cal = _calendar(s, spec)
    if s.get(CalendarYear, (cal.id, day.year)) is None:
        raise NotCovered(f"{name} has no published dates for {day.year}")
    row = s.scalar(
        select(CalendarDay).where(
            CalendarDay.calendar_id == cal.id, CalendarDay.day == day, CalendarDay.valid_to.is_(None)
        )
    )
    if row is None:
        return out | {"business_day": True, "status": "open"}
    out |= {"business_day": row.status != "closed", "status": row.status, "holiday": row.holiday}
    if row.close_time is not None:
        out["close_time"] = row.close_time.isoformat(timespec="minutes")
    return out
