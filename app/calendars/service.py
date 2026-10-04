"""Calendar sources: capture, parse, and record each as near-raw rows.

mkt-data is the ingestion layer (docs/phase-2.md). For every calendar source:

1. Fetch it. Every attempt is a `source_check` row. New content (by SHA-256,
   or by visible text for pages whose markup changes on every request)
   becomes a `capture` row, stored byte for byte and never changed; the same
   content as last time records the check only.
2. Parse the latest capture. A parse error leaves the raw capture in place,
   so a fixed parser can re-run on it (`reparse`).
3. Record the parse as the source's near-raw rows (near_raw.py): its covered
   years and its closed and early-close weekdays, as that source states them,
   with history.

Building one calendar per market from its sources (precedence, the
projection's whole-year handover, coverage, the business-day answer) is
calendar-svc's job since phase 2, step A5; it reads these rows over gRPC
(app/grpc_server.py, CalendarSources). CALENDARS here groups the sources by
the calendar they're captured for, highest precedence first, as calendar-svc
lists them.

A source can have no parser yet (`parse=None`): it's fetched and kept raw,
and records nothing. That's how a new document is first captured, so its
parser can be written against the real bytes.

A `repo:` source is a rules file in this repo (app/calendars/rules.py): its
"fetch" reads the file, so its captures are the rule set's versions. A
projected source (`projected=True`) is a rules file run forward to 2100.
"""

import hashlib
from collections.abc import Callable
from dataclasses import dataclass

import httpx2
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.calendars import fed, near_raw, nyfed, nyse, nyse_history, rules, sifma, sifma_history, text
from app.calendars.parsed import ParsedCalendar, ParseError
from app.models import Capture, Source, SourceCheck

USER_AGENT = "mkt-data/1 (personal market data platform; bcalaway)"
FETCH_TIMEOUT_SECONDS = 60


@dataclass(frozen=True)
class SourceSpec:
    name: str
    url: str
    description: str
    parse: Callable[[bytes], ParsedCalendar] | None  # None: captured raw, not parsed yet
    projected: bool = False  # a rules file run forward to 2100 (calendar-svc fills only uncovered years with it)
    # True: a fetch whose visible text matches the last capture's is a check,
    # not a new capture, even if the bytes differ. For pages whose markup
    # changes on every request (K.8). Not for pages whose data might sit in
    # blocks the text view skips (scripts, templates).
    dedupe_on_text: bool = False


@dataclass(frozen=True)
class CalendarSpec:
    """The sources captured for a calendar, highest precedence first (as calendar-svc ranks them)."""

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
                "FED-K8", fed.URL, "Federal Reserve Board, K.8 Holidays Observed (current year + 4)", fed.parse,
                dedupe_on_text=True,
            ),
            *(
                SourceSpec(
                    f"FED-NYFED-{year}", url, f"NY Fed holiday-schedule circular for {year}", nyfed.parse,
                    # Like K.8, the NY Fed's pages change markup on every fetch while
                    # the text stays the same (captures #15 and #23, 2026-10-04).
                    dedupe_on_text=True,
                )
                for year, url in fed.NYFED_CIRCULARS.items()
            ),
            SourceSpec(
                "FED-RULES", f"{rules.REPO_PREFIX}fed.json",
                "Federal holidays as the Reserve Banks observe them, 1986-2025 (rules, cited)", rules.parse,
            ),
            SourceSpec(
                "FED-PROJECTED", f"{rules.REPO_PREFIX}fed_projected.json",
                "FED projected from its rules to 2100 (years K.8 doesn't cover)", rules.parse, projected=True,
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
            SourceSpec(
                "SIFMA-US-PROJECTED", f"{rules.REPO_PREFIX}sifma_us_projected.json",
                "SIFMA-US full closes projected to 2100 (years SIFMA hasn't published)", rules.parse, projected=True,
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
                "NYSE-HISTORY", nyse.HISTORY_URL,
                "NYSE, History of New York Stock Exchange Holidays (PDF; its special closings, 1990-2010)",
                nyse_history.parse,
            ),
            SourceSpec(
                "NYSE-RULES", f"{rules.REPO_PREFIX}nyse.json",
                "NYSE holidays, early closes and one-off closes, 1990-2025 (rules, cited)", rules.parse,
            ),
            SourceSpec(
                "NYSE-PROJECTED", f"{rules.REPO_PREFIX}nyse_projected.json",
                "NYSE full closes projected to 2100 (years the hours page doesn't cover)", rules.parse, projected=True,
            ),
        ),
    ),
}


def source_kind(src: SourceSpec) -> str:
    """'published' (a publisher's page or file), 'rules' (a rules file) or 'projected'."""
    if src.projected:
        return "projected"
    return "rules" if src.url.startswith(rules.REPO_PREFIX) else "published"


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


def fetch(url: str) -> tuple[int, str | None, bytes]:
    try:
        r = httpx2.get(
            url, timeout=FETCH_TIMEOUT_SECONDS, follow_redirects=True, headers={"User-Agent": USER_AGENT}
        )
    except httpx2.HTTPError as e:
        raise SourceFetchError(f"{url}: {e}") from None
    if r.status_code != 200:
        raise SourceFetchError(f"{url}: HTTP {r.status_code}")
    return r.status_code, r.headers.get("content-type"), r.content


def _read_repo(url: str) -> tuple[int, str, bytes]:
    try:
        return 200, "application/json", rules.read(url)
    except FileNotFoundError as e:
        raise SourceFetchError(f"{url}: {e}") from None


def capture(
    s: Session, spec: SourceSpec, fetcher=None, *, url: str | None = None, period: str | None = None
) -> tuple[Capture, bool, SourceCheck]:
    """Fetch the source; store the content if it's new. Returns (latest capture, is_new, the check).

    A source fetched a period at a time (Treasury's par curve by month) passes
    that period's `url` and the `period` ("2026-10"): "new" then means new for
    that source and period.
    """
    src = _source(s, spec)
    url = url or src.url
    try:
        if url.startswith(rules.REPO_PREFIX):
            status, ctype, body = _read_repo(url)
        else:
            status, ctype, body = (fetcher or fetch)(url)
        if not body:
            # A 200 with nothing in it (H.15 once, 2026-10-04) is a failed
            # fetch, not content: storing it would hide the real page until
            # the next run. Raised so the job fails and Airflow retries.
            raise SourceFetchError(f"{url}: empty response")
    except SourceFetchError as e:
        s.add(SourceCheck(source_id=src.id, outcome="error", detail=str(e)[:2000], period=period))
        s.commit()
        raise
    sha = hashlib.sha256(body).hexdigest()
    same_period = Capture.period.is_(None) if period is None else Capture.period == period
    last = s.scalar(
        select(Capture).where(Capture.source_id == src.id, same_period).order_by(Capture.id.desc()).limit(1)
    )
    if last is not None and last.sha256 == sha:
        check = SourceCheck(source_id=src.id, outcome="unchanged", capture_id=last.id, period=period)
        s.add(check)
        s.flush()
        return last, False, check
    if last is not None and spec.dedupe_on_text and _visible_text(last.body) == _visible_text(body):
        check = SourceCheck(
            source_id=src.id, outcome="unchanged", capture_id=last.id, period=period,
            detail=f"markup changed, visible text identical (sha256 {sha})",
        )
        s.add(check)
        s.flush()
        return last, False, check
    cap = Capture(
        source_id=src.id, http_status=status, content_type=ctype, sha256=sha, size_bytes=len(body), body=body,
        period=period,
    )
    s.add(cap)
    s.flush()
    check = SourceCheck(source_id=src.id, outcome="new", capture_id=cap.id, period=period)
    s.add(check)
    s.flush()
    return cap, True, check


def _visible_text(body: bytes) -> list[str]:
    return text.lines(body.decode("utf-8", errors="replace"))


def latest_capture(s: Session, spec: SourceSpec) -> Capture | None:
    src = _source(s, spec)
    return s.scalar(select(Capture).where(Capture.source_id == src.id).order_by(Capture.id.desc()).limit(1))


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


def _parse_and_apply(s: Session, spec: CalendarSpec, rank: int, src: SourceSpec, cap: Capture,
                     check: SourceCheck) -> dict:
    """Parse the capture and record it as near-raw rows, with the parse's outcome on the check."""
    try:
        parsed: ParsedCalendar = src.parse(cap.body)
    except ParseError as e:
        check.parse_outcome, check.parse_detail = "error", str(e)[:2000]
        s.commit()  # kept even though _run rolls back what follows
        raise
    out = {"years": list(parsed.years), "days": len(parsed.days)} | near_raw.apply_source(s, cap, parsed)
    check.parse_outcome = "ok"
    s.commit()
    return out


def run_capture(s: Session, name: str, fetcher=None) -> dict:
    def step(spec: CalendarSpec, rank: int, src: SourceSpec) -> dict:
        cap, is_new, check = capture(s, src, fetcher)
        # Commit the raw capture (and its check) before parsing: a parse error
        # must never lose what was fetched.
        s.commit()
        if src.parse is None:
            return {"capture_id": cap.id, "new_capture": is_new, "parsed": False, "note": NOT_PARSED}
        return {"capture_id": cap.id, "new_capture": is_new} | _parse_and_apply(s, spec, rank, src, cap, check)

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
        check = SourceCheck(source_id=cap.source_id, outcome="reparse", capture_id=cap.id)
        s.add(check)
        s.flush()
        return {"capture_id": cap.id, "new_capture": False} | _parse_and_apply(s, spec, rank, src, cap, check)

    return _run(s, name, step)


def run_near_raw_rebuild(s: Session, name: str) -> dict:
    """Rebuild every parsed source's near-raw rows from all its captures (near_raw.rebuild)."""
    spec = CALENDARS[name]
    results = []
    for src in spec.sources:
        if src.parse is None:
            results.append({"source": src.name, "parsed": False, "note": NOT_PARSED})
            continue
        _source(s, src)
        results.append(near_raw.rebuild(s, src.name, src.parse))
    return {"calendar": name, "sources": results}
