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

from app.calendars import (
    fed,
    govuk,
    jpcao,
    nbo,
    near_raw,
    nyfed,
    nyse,
    nyse_history,
    rules,
    sifma,
    sifma_history,
    six_sic,
    text,
)
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
    # Like dedupe_on_text, for other formats: a fetch whose view equals the
    # last capture's view is a check, not a new capture. For JSON answers that
    # stamp the request time (BLS's responseTime). The bytes kept are the
    # first fetch's, unchanged.
    dedupe_view: Callable[[bytes], object] | None = None
    # What's taken from the source and who reads it, for the Sources screen (docs/phase-3.md, step 8). Calendar
    # sources leave it empty: their text comes from their calendar and rank (app/source_status.py).
    pulls: str = ""


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


SIX_SIC_URL = ("https://www.six-group.com/dam/download/banking-services/interbank-clearing/en/payment_services/sic/"
               "banking-holidays.pdf")


NO_NBO_URL = "https://www.norges-bank.no/en/topics/Norges-Banks-settlement-system/Settlement-days/"
BR_ANBIMA_URL = "https://www.anbima.com.br/feriados/arqs/feriados_nacionais.xls"


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
    # CME's business days (docs/phase-4.md, "Calendars"). No published source: CME's terms rule out capturing
    # its holiday pages, so the rules files cite CME's notices, read by hand, and are extended a year at a time.
    "CME-IR": CalendarSpec(
        name="CME-IR",
        description="CME Group U.S. interest rate futures: days with a trade date and settlement",
        timezone="America/Chicago",
        sources=(
            SourceSpec(
                "CME-IR-RULES", f"{rules.REPO_PREFIX}cme_ir.json",
                "CME interest rate futures holidays and one-off closes, 1990-2026 (rules, cited from CME notices)",
                rules.parse,
            ),
            SourceSpec(
                "CME-IR-PROJECTED", f"{rules.REPO_PREFIX}cme_ir_projected.json",
                "CME-IR full closes projected to 2100", rules.parse, projected=True,
            ),
        ),
    ),
    "GB": CalendarSpec(
        name="GB",
        description="England and Wales bank holidays (London): closed weekdays",
        timezone="Europe/London",
        sources=(
            SourceSpec("GB-GOVUK", govuk.URL, "gov.uk, UK bank holidays (JSON, England and Wales; 2019 on)", govuk.parse),
            SourceSpec(
                "GB-RULES", f"{rules.REPO_PREFIX}gb.json",
                "England and Wales bank holidays, 1990-2018 (rules and royal proclamations, cited)", rules.parse,
            ),
            SourceSpec(
                "GB-PROJECTED", f"{rules.REPO_PREFIX}gb_projected.json",
                "GB bank holidays projected to 2100 (years gov.uk doesn't list)", rules.parse, projected=True,
            ),
        ),
    ),
    # The euro's settlement calendar (docs/phase-4.md, "Calendars"): fixed by the ECB since 2002 "until further
    # notice", so the rules file is the calendar itself, to 2100.
    "TARGET": CalendarSpec(
        name="TARGET",
        description="TARGET/T2 closing days (euro settlement)",
        timezone="Europe/Berlin",
        sources=(
            SourceSpec("TARGET-RULES", f"{rules.REPO_PREFIX}target.json",
                       "ECB TARGET closing days, 1999-2100 (fixed since 2002; cited)", rules.parse),
        ),
    ),
    # Canada's payments calendar, for the Canadian dollar futures (docs/phase-4.md, "Calendars"): Payments Canada
    # publishes no capturable list, so the rules file is the calendar, checked against banks' published lists.
    "CA": CalendarSpec(
        name="CA",
        description="Canada payments holidays (Payments Canada, Toronto)",
        timezone="America/Toronto",
        sources=(
            SourceSpec("CA-RULES", f"{rules.REPO_PREFIX}ca.json",
                       "Canada's national payments holidays, 1990-2100 (rules; cited)", rules.parse),
        ),
    ),
    # Zurich: SIC's banking holidays, for the Swiss franc futures (docs/phase-4.md, "Calendars"). SIX's PDF lists next
    # year (app/calendars/six_sic.py); the cited rules run 1990-2100.
    "CH": CalendarSpec(
        name="CH",
        description="Swiss franc payments holidays (SIC, Zurich)",
        timezone="Europe/Zurich",
        sources=(
            SourceSpec("SIX-SIC", SIX_SIC_URL, "SIX, SIC banking holidays (PDF, next year)", six_sic.parse),
            SourceSpec("CH-RULES", f"{rules.REPO_PREFIX}ch.json",
                       "SIC banking holidays, 1990-2100 (rules; cited)", rules.parse),
        ),
    ),
    # Sydney, for the Australian dollar futures (docs/phase-4.md, "Calendars"): NSW's public holidays and Bank Holiday.
    # No capturable list covers them all (NSW's own is a web page, a year or two ahead), so the cited rules are the
    # calendar, checked against ANZ's and NSW's published lists.
    "AU": CalendarSpec(
        name="AU",
        description="Australian dollar settlement holidays (Sydney)",
        timezone="Australia/Sydney",
        sources=(
            SourceSpec("AU-RULES", f"{rules.REPO_PREFIX}au.json",
                       "Sydney (NSW) public and bank holidays, 1990-2100 (rules; cited)", rules.parse),
        ),
    ),
    # New Zealand, for the NZ dollar futures (docs/phase-4.md, "Calendars"): the national holidays ESAS closes for (the
    # Auckland and Wellington anniversary days are settlement days). No capturable list, so the cited rules are the
    # calendar.
    "NZ": CalendarSpec(
        name="NZ",
        description="New Zealand dollar settlement holidays (national; ESAS)",
        timezone="Pacific/Auckland",
        sources=(
            SourceSpec("NZ-RULES", f"{rules.REPO_PREFIX}nz.json",
                       "New Zealand national public holidays, 1990-2100 (rules; cited)", rules.parse),
        ),
    ),
    # Stockholm, for the krona futures (docs/phase-4.md, "Calendars"): the banks' closing days, cited rules.
    "SE": CalendarSpec(
        name="SE",
        description="Swedish krona settlement holidays (Stockholm banks)",
        timezone="Europe/Stockholm",
        sources=(
            SourceSpec("SE-RULES", f"{rules.REPO_PREFIX}se.json",
                       "Swedish bank holidays, 1990-2100 (rules; cited)", rules.parse),
        ),
    ),
    # Oslo, for the krone futures (docs/phase-4.md, "Calendars"): Norges Bank's settlement days page (the current year;
    # app/calendars/nbo.py) and the cited rules.
    "NO": CalendarSpec(
        name="NO",
        description="Norwegian krone settlement holidays (NBO, Oslo)",
        timezone="Europe/Oslo",
        sources=(
            SourceSpec("NO-NBO", NO_NBO_URL, "Norges Bank, NBO settlement days (web page, this year)", nbo.parse,
                       dedupe_on_text=True),
            SourceSpec("NO-RULES", f"{rules.REPO_PREFIX}no.json",
                       "NBO closing days, 1990-2100 (rules; cited)", rules.parse),
        ),
    ),
    # Copenhagen, for the krone (docs/phase-4.md, "Calendars"): the banks' closing days, cited rules.
    "DK": CalendarSpec(
        name="DK",
        description="Danish krone settlement holidays (Copenhagen banks)",
        timezone="Europe/Copenhagen",
        sources=(
            SourceSpec("DK-RULES", f"{rules.REPO_PREFIX}dk.json",
                       "Danish bank holidays, 1990-2100 (rules; cited)", rules.parse),
        ),
    ),
    # Mexico City, for the peso futures (docs/phase-4.md, "Calendars"): the CNBV's closing days, cited rules.
    "MX": CalendarSpec(
        name="MX",
        description="Mexican peso settlement holidays (CNBV, Mexico City)",
        timezone="America/Mexico_City",
        sources=(
            SourceSpec("MX-RULES", f"{rules.REPO_PREFIX}mx.json",
                       "CNBV bank closing days, 1990-2100 (rules; cited)", rules.parse),
        ),
    ),
    # The emerging-market FX futures' calendars (docs/phase-4.md, step 2d): cited rules, as for the G10.
    # Brazil: the national holidays, with ANBIMA's spreadsheet of every year 2001-2099 captured raw (its parser
    # follows against a real capture).
    "BR": CalendarSpec(
        name="BR",
        description="Brazilian real settlement holidays (national holidays; ANBIMA)",
        timezone="America/Sao_Paulo",
        sources=(
            SourceSpec("BR-ANBIMA", BR_ANBIMA_URL, "ANBIMA, national holidays 2001-2099 (spreadsheet)", None),
            SourceSpec("BR-RULES", f"{rules.REPO_PREFIX}br.json",
                       "Brazilian national holidays, 1990-2100 (rules; cited)", rules.parse),
        ),
    ),
    "ZA": CalendarSpec(
        name="ZA",
        description="South African rand settlement holidays (SAMOS, Johannesburg)",
        timezone="Africa/Johannesburg",
        sources=(
            SourceSpec("ZA-RULES", f"{rules.REPO_PREFIX}za.json",
                       "South African public holidays, 1995-2100 (rules and declared days; cited)", rules.parse),
        ),
    ),
    "PL": CalendarSpec(
        name="PL",
        description="Polish zloty settlement holidays (SORBNET, Warsaw)",
        timezone="Europe/Warsaw",
        sources=(
            SourceSpec("PL-RULES", f"{rules.REPO_PREFIX}pl.json",
                       "Polish statutory days off, 1990-2100 (rules; cited)", rules.parse),
        ),
    ),
    "CZ": CalendarSpec(
        name="CZ",
        description="Czech koruna settlement holidays (CERTIS, Prague)",
        timezone="Europe/Prague",
        sources=(
            SourceSpec("CZ-RULES", f"{rules.REPO_PREFIX}cz.json",
                       "Czech public holidays, 1990-2100 (rules; cited)", rules.parse),
        ),
    ),
    "HU": CalendarSpec(
        name="HU",
        description="Hungarian forint settlement holidays (VIBER, Budapest)",
        timezone="Europe/Budapest",
        sources=(
            SourceSpec("HU-RULES", f"{rules.REPO_PREFIX}hu.json",
                       "Hungarian public holidays and decreed bridge days, 1990-2100 (rules; cited)", rules.parse),
        ),
    ),
    # Tokyo's bank holidays, for the yen futures (docs/phase-4.md, "Calendars"): the Cabinet Office's national
    # holidays (1955 to next year), the banks' December 31-January 3 beside them, and a projection.
    "JP": CalendarSpec(
        name="JP",
        description="Japan bank holidays (Tokyo): national holidays and December 31-January 3",
        timezone="Asia/Tokyo",
        sources=(
            SourceSpec("JP-CAO", jpcao.URL, "Cabinet Office, national holidays CSV (1955 to next year)", jpcao.parse),
            SourceSpec(
                "JP-BANK", f"{rules.REPO_PREFIX}jp_bank.json",
                "Japan bank holidays December 31 and January 2-3, 1990-2100 (Banking Act order; adds dates only)",
                rules.parse,
            ),
            SourceSpec(
                "JP-PROJECTED", f"{rules.REPO_PREFIX}jp_projected.json",
                "Japan national holidays projected to 2100 (years the CSV doesn't list)", rules.parse, projected=True,
            ),
        ),
    ),
    "CME-FX": CalendarSpec(
        name="CME-FX",
        description="CME Group FX futures: days with a trade date and settlement",
        timezone="America/Chicago",
        sources=(
            SourceSpec(
                "CME-FX-RULES", f"{rules.REPO_PREFIX}cme_fx.json",
                "CME FX futures holidays and one-off closes, 1990-2026 (rules, cited from CME notices)", rules.parse,
            ),
            SourceSpec(
                "CME-FX-PROJECTED", f"{rules.REPO_PREFIX}cme_fx_projected.json",
                "CME-FX full closes projected to 2100", rules.parse, projected=True,
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
    if last is not None and spec.dedupe_view is not None and _same_view(spec.dedupe_view, last.body, body):
        check = SourceCheck(
            source_id=src.id, outcome="unchanged", capture_id=last.id, period=period,
            detail=f"bytes changed, content identical (sha256 {sha})",
        )
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


def _same_view(view, old: bytes, new: bytes) -> bool:
    try:
        return view(old) == view(new)
    except ValueError:  # either side unreadable in that view: keep the new bytes
        return False


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
