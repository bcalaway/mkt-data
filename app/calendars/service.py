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

A calendar can have several sources, highest precedence first (SIFMA-US:
its current page, then its archive, then its 1996-2019 PDF). Each is fetched
and applied on its own; a source never overrides a date a higher one holds,
and only closes off rows it wrote itself (`apply`). One source failing
doesn't stop the others.

A source can have no parser yet (`parse=None`): it's fetched and kept raw,
and applies nothing. That's how a new document is first captured, so its
parser can be written against the real bytes.

A `repo:` source is a rules file in this repo (app/calendars/rules.py): its
"fetch" reads the file, so its captures are the rule set's versions.
"""

import hashlib
from collections.abc import Callable
from dataclasses import dataclass
from datetime import UTC, date, datetime

import httpx
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.calendars import fed, nyse, rules, sifma, sifma_history
from app.calendars.parsed import Day, ParsedCalendar, ParseError, diff
from app.models import Calendar, CalendarDay, CalendarYear, Capture, Source, SourceCheck

USER_AGENT = "mkt-data/1 (personal market data platform; bcalaway)"
FETCH_TIMEOUT_SECONDS = 60


@dataclass(frozen=True)
class SourceSpec:
    name: str
    url: str
    description: str
    parse: Callable[[bytes], ParsedCalendar] | None  # None: captured raw, not parsed yet


@dataclass(frozen=True)
class CalendarSpec:
    """A calendar and its sources, highest precedence first.

    A calendar can have several sources (a publisher's current page, its
    archive, rules for older years). Each source's parse is applied on its
    own; where two sources list the same date, the higher one's row stands.
    """

    name: str
    description: str
    timezone: str
    sources: tuple[SourceSpec, ...]

    @property
    def source_names(self) -> list[str]:
        return [x.name for x in self.sources]


CALENDARS: dict[str, CalendarSpec] = {
    "FED": CalendarSpec(
        name="FED",
        description="Federal Reserve Banks and Fedwire: closed weekdays",
        timezone="America/New_York",
        sources=(
            SourceSpec(
                "FED-K8", fed.URL, "Federal Reserve Board, K.8 Holidays Observed (current year + 4)", fed.parse
            ),
            SourceSpec(
                "FED-RULES", f"{rules.REPO_PREFIX}fed.json",
                "Federal holidays as the Reserve Banks observe them, 1986-2025 (rules, cited)", rules.parse,
            ),
        ),
    ),
    "SIFMA-US": CalendarSpec(
        name="SIFMA-US",
        description="US bond market (SIFMA recommendations): full closes and early closes",
        timezone="America/New_York",
        sources=(
            SourceSpec(
                "SIFMA-US-HOLIDAYS", sifma.URL,
                "SIFMA, U.S. Holiday Recommendations (published years only)", sifma.parse,
            ),
            SourceSpec(
                "SIFMA-US-ARCHIVE", sifma.ARCHIVE_URL,
                "SIFMA, U.S. Holiday Archive (recent past years)", sifma.parse_archive,
            ),
            SourceSpec(
                "SIFMA-US-HISTORY", sifma.HISTORY_URL,
                "SIFMA, historical U.S. holiday recommendations PDF (1996-2019)", sifma_history.parse,
            ),
            SourceSpec(
                "SIFMA-US-EXCEPTIONS", f"{rules.REPO_PREFIX}sifma_us_exceptions.json",
                "SIFMA unscheduled recommendations its documents don't list (cited)", rules.parse,
            ),
        ),
    ),
    "NYSE": CalendarSpec(
        name="NYSE",
        description="NYSE equities: full closes and early closes (equities close time)",
        timezone="America/New_York",
        sources=(
            SourceSpec("NYSE-HOURS", nyse.URL, "NYSE, Holidays & Trading Hours (current year + 2)", nyse.parse),
            SourceSpec(
                "NYSE-RULES", f"{rules.REPO_PREFIX}nyse.json",
                "NYSE holidays, early closes and one-off closes, 1990-2025 (rules, cited)", rules.parse,
            ),
        ),
    ),
}


SOURCES: dict[str, SourceSpec] = {src.name: src for cal in CALENDARS.values() for src in cal.sources}

NOT_PARSED = "kept raw; this source has no parser yet"


class SourceFetchError(RuntimeError):
    pass


class NotCovered(LookupError):
    pass


def _source(s: Session, spec: SourceSpec) -> Source:
    src = s.scalar(select(Source).where(Source.name == spec.name))
    if src is None:
        src = Source(name=spec.name, url=spec.url, description=spec.description)
        s.add(src)
        s.flush()
    elif src.url != spec.url or src.description != spec.description:
        src.url, src.description = spec.url, spec.description
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


def _read_repo(url: str) -> tuple[int, str, bytes]:
    try:
        return 200, "application/json", rules.read(url)
    except FileNotFoundError as e:
        raise SourceFetchError(f"{url}: {e}") from None


def capture(s: Session, spec: SourceSpec, fetcher=None) -> tuple[Capture, bool]:
    """Fetch the source; store the content if it's new. Returns (latest capture, is_new)."""
    src = _source(s, spec)
    try:
        if src.url.startswith(rules.REPO_PREFIX):
            status, ctype, body = _read_repo(src.url)
        else:
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


def latest_capture(s: Session, spec: SourceSpec) -> Capture | None:
    src = _source(s, spec)
    return s.scalar(select(Capture).where(Capture.source_id == src.id).order_by(Capture.id.desc()).limit(1))


def _ranks(s: Session, cal_spec: CalendarSpec) -> dict[int, int]:
    """capture id -> its source's rank in the calendar (0 = highest precedence)."""
    rank_by_source = {_source(s, x).id: i for i, x in enumerate(cal_spec.sources)}
    rows = s.execute(select(Capture.id, Capture.source_id).where(Capture.source_id.in_(rank_by_source)))
    return {cid: rank_by_source[sid] for cid, sid in rows}


def apply(s: Session, cal_spec: CalendarSpec, rank: int, cap: Capture, parsed: ParsedCalendar) -> dict:
    """Apply one source's parse to the calendar, with history and precedence.

    Within the calendar, this source (at `rank`) may write a date unless a
    higher-precedence source's row holds it, and may close off only the rows
    it wrote itself. Coverage years work the same way: a year stays credited
    to the highest-precedence source that covers it.
    """
    cal = _calendar(s, cal_spec)
    now = datetime.now(UTC)
    ranks = _ranks(s, cal_spec)
    lowest = len(cal_spec.sources)  # rows from a source the calendar no longer lists
    rows = s.scalars(
        select(CalendarDay).where(CalendarDay.calendar_id == cal.id, CalendarDay.valid_to.is_(None))
    ).all()
    by_day = {r.day: r for r in rows}
    current = {r.day: Day(r.day, r.status, r.holiday, r.close_time) for r in rows}
    own = {r.day for r in rows if ranks.get(r.capture_id, lowest) == rank}
    blocked = {r.day for r in rows if ranks.get(r.capture_id, lowest) < rank}
    d = diff(current, parsed, own=own, blocked=blocked)
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
    years = {y.year: y for y in s.scalars(select(CalendarYear).where(CalendarYear.calendar_id == cal.id))}
    new_years = []
    for y in parsed.years:
        row = years.get(y)
        if row is None:
            s.add(CalendarYear(calendar_id=cal.id, year=y, capture_id=cap.id))
            new_years.append(y)
        elif ranks.get(row.capture_id, lowest) >= rank:
            row.capture_id = cap.id
    out = {
        "years": list(parsed.years),
        "new_years": new_years,
        "closed_days": len(parsed.days),
        "added": len(d.added),
        "changed": [x.day.isoformat() for x in d.changed],
        "removed": [x.isoformat() for x in d.removed],
    }
    if d.held:
        out["held_by_higher_source"] = [x.isoformat() for x in d.held]
    return out


def _run(s: Session, name: str, step) -> dict:
    """Run `step` for each source in precedence order; raise the first error at the end.

    One source failing (a fetch error, a page the parser rejects) doesn't
    stop the others: each source's work is committed on its own.
    """
    spec = CALENDARS[name]
    results, errors = [], []
    for rank, src in enumerate(spec.sources):
        try:
            results.append({"source": src.name} | step(spec, rank, src))
        except (SourceFetchError, ParseError) as e:
            s.rollback()
            results.append({"source": src.name, "error": str(e)})
            errors.append((src.name, e))
    if errors:
        src_name, e = errors[0]
        raise type(e)(f"{src_name}: {e}")
    return {"calendar": name, "sources": results}


def run_capture(s: Session, name: str, fetcher=None) -> dict:
    def step(spec: CalendarSpec, rank: int, src: SourceSpec) -> dict:
        cap, is_new = capture(s, src, fetcher)
        # Commit the raw capture (and its check) before parsing: a parse error
        # must never lose what was fetched.
        s.commit()
        if src.parse is None:
            return {"capture_id": cap.id, "new_capture": is_new, "parsed": False, "note": NOT_PARSED}
        out = {"capture_id": cap.id, "new_capture": is_new} | apply(s, spec, rank, cap, src.parse(cap.body))
        s.commit()
        return out

    return _run(s, name, step)


def run_reparse(s: Session, name: str) -> dict:
    spec = CALENDARS[name]
    if all(latest_capture(s, src) is None for src in spec.sources):
        raise NotCovered(f"{name}: nothing captured yet")

    def step(spec: CalendarSpec, rank: int, src: SourceSpec) -> dict:
        cap = latest_capture(s, src)
        if cap is None:
            return {"skipped": "nothing captured yet"}
        if src.parse is None:
            return {"capture_id": cap.id, "new_capture": False, "parsed": False, "note": NOT_PARSED}
        out = {"capture_id": cap.id, "new_capture": False} | apply(s, spec, rank, cap, src.parse(cap.body))
        s.commit()
        return out

    return _run(s, name, step)


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
