"""Treasury securities sources (docs/phase-3.md, step 1): captured raw, no parsers yet.

As in phase 2, the raw history starts accumulating before any parser exists,
so the parsers are written against real bytes. Claude's web tools can't read
TreasuryDirect (robots.txt) and the sandbox can't reach either Treasury host,
so the first captures on the hub, read with home-mcp's mkt_data_capture_text,
are where the formats get checked.

Each source is fetched a period at a time, and each period is its own
capture (`capture.period`); the period's kind depends on the source:

- TD-SECURITIES (month of auction date): TreasuryDirect's securities web API,
  every announced and auctioned marketable security, with its terms, auction
  results, TIPS and FRN details and the principal STRIPS CUSIP
  (`CorpusCusip`). Primary for terms and auctions. A month is refetched while
  it can still change (announcements come up to a week or so ahead, results
  on auction day).
- TD-PRICES (day): FedInvest's prices for Treasury securities, every
  marketable CUSIP's buy, sell and end-of-day price for one date. The page's
  form posts the date with a session-bound CSRF token, so a fetch reads the
  form first (for the session cookie and token), then posts; the results
  page is what's kept (checked 2026-10-06 in the browser: a bare post gets
  403).
- FD-AUCTIONS (month of auction date): Fiscal Data's Treasury securities
  auctions data, the same auction records through a documented, paged API.
  Cross-check and fallback.
- FD-MSPD-STRIPS (month of record date): Fiscal Data's Monthly Statement of
  the Public Debt, the table of securities held in stripped form. STRIPS
  identity and amounts stripped.
- BLS-CPI (year): CPI-U, not seasonally adjusted (CUUR0000SA0), from the BLS
  public data API. TIPS reference CPIs and index ratios.

All but BLS publish on U.S. Government Securities Business Days (SIFMA-US);
BLS on Federal business days (FED). Those calendars label the metrics.
"""

import json
import re
from collections.abc import Callable
from dataclasses import dataclass
from datetime import date, datetime, timedelta
from typing import Literal
from zoneinfo import ZoneInfo

import httpx2
from sqlalchemy.orm import Session

from app.calendars import service
from app.calendars.parsed import ParseError
from app.calendars.service import SourceFetchError, SourceSpec
from app.rates import near_raw
from app.securities import parsers, records

EASTERN = ZoneInfo("America/New_York")
Kind = Literal["day", "month", "year"]

TD_SECURITIES_URL = (
    "https://www.treasurydirect.gov/TA_WS/securities/search"
    "?format=json&dateFieldName=auctionDate&startDate={first_us}&endDate={last_us}"
)
# FedInvest's "Historical Prices" form: GET it for a session and CSRF token, then
# POST priceDate (YYYY-MM-DD) to the same URL. See post_fedinvest().
TD_PRICES_URL = "https://www.treasurydirect.gov/GA-FI/FedInvest/selectSecurityPriceDate"
CSRF = re.compile(rb'name="_csrf"[^>]*?value="([^"]+)"|value="([^"]+)"[^>]*?name="_csrf"')
FISCAL_DATA = "https://api.fiscaldata.treasury.gov/services/api/fiscal_service"
FD_AUCTIONS_URL = (
    FISCAL_DATA + "/v1/accounting/od/auctions_query"
    "?filter=auction_date:gte:{first},auction_date:lte:{last}&sort=auction_date&page[size]=10000"
)
FD_MSPD_STRIPS_URL = (
    FISCAL_DATA + "/v1/debt/mspd/mspd_table_5"
    "?filter=record_date:gte:{first},record_date:lte:{last}&page[size]=10000"
)
BLS_CPI_URL = "https://api.bls.gov/publicAPI/v2/timeseries/data/CUUR0000SA0?startyear={year}&endyear={year}"


# What BLS answers instead of data when it won't serve a request (most often: the 25 keyless requests a day are used
# up). The daily capture DAG looks for it in a failed fetch and doesn't retry or fail over it.
NOT_SERVED = "REQUEST_NOT_PROCESSED"


def fetch_bls(url: str) -> tuple[int, str | None, bytes]:
    """A GET whose answer BLS refused to serve is a failed fetch, not a capture: nothing stored, nothing to parse.

    BLS answers HTTP 200 with status REQUEST_NOT_PROCESSED and a message ("...daily threshold for total number of
    requests allocated per user..."). Kept as a capture, the parser rejected it and "Market data parse failed" fired
    until BLS next served (2026-10-07, after the 1996-2015 history used the day's requests).
    """
    status, ctype, body = service.fetch(url)
    try:
        doc = json.loads(body)
    except ValueError:
        return status, ctype, body  # not JSON at all: the parser says what's wrong with it
    if isinstance(doc, dict) and doc.get("status") == NOT_SERVED:
        message = " ".join(str(m) for m in doc.get("message") or [])[:300]
        raise service.SourceFetchError(f"BLS didn't serve the request ({NOT_SERVED}): {message}")
    return status, ctype, body


def bls_view(body: bytes) -> object:
    """BLS's answer without what changes on every request (responseTime, message)."""
    try:
        doc = json.loads(body)
    except (UnicodeDecodeError, json.JSONDecodeError) as e:
        raise ValueError(str(e)) from None
    if isinstance(doc, dict):
        doc = {k: v for k, v in doc.items() if k not in ("responseTime", "message")}
    return doc


@dataclass(frozen=True)
class SecuritiesSource:
    spec: SourceSpec  # name, url template, description, parser
    kind: Kind  # what a period is: a day, a month or a year
    # Which near-raw table its parse goes to; "curve" (the SPGMI swap curves): both, the parse a pair (observations,
    # records).
    shape: Literal["records", "observations", "curve"]
    calendar: str  # publication calendar (calendar-svc), for metric labels
    first_period: str  # the earliest period to ask for; the real first one is found in the backfill
    ahead: int = 0  # periods past the current one that may already have data (announcements)
    form: bool = False  # fetched by posting FedInvest's form, not a GET
    fetch: Callable[[str], tuple[int, str | None, bytes]] | None = None  # a GET that knows the source's refusals

    def bounds(self, period: str) -> tuple[date, date]:
        if self.kind == "day":
            d = date.fromisoformat(period)
            return d, d
        if self.kind == "year":
            y = int(period)
            return date(y, 1, 1), date(y, 12, 31)
        y, m = (int(x) for x in period.split("-"))
        nxt = date(y + (m == 12), m % 12 + 1, 1)
        return date(y, m, 1), nxt - timedelta(days=1)

    def url(self, period: str) -> str:
        first, last = self.bounds(period)
        return self.spec.url.format(
            first=first.isoformat(), last=last.isoformat(),
            first_us=first.strftime("%m/%d/%Y"), last_us=last.strftime("%m/%d/%Y"), year=first.year,
            ymd=first.strftime("%Y%m%d"),
        )


def _spec(name: str, url: str, description: str, parse, **kw) -> SourceSpec:
    return SourceSpec(name, url, description, parse, **kw)


SOURCES: dict[str, SecuritiesSource] = {
    "TD-SECURITIES": SecuritiesSource(
        _spec("TD-SECURITIES", TD_SECURITIES_URL,
              "TreasuryDirect securities web API, announced and auctioned securities (JSON, by month of auction)",
              parsers.parse_td_securities,
              pulls=('Every announced and auctioned marketable security by auction: terms, dates and results. '
                     'secmaster-svc reads them: the Treasury securities, their terms, auctions, on-the-run aliases and'
                     ' STRIPS CUSIPs.')),
        kind="month", shape="records", calendar="SIFMA-US", first_period="1979-01", ahead=1,
    ),
    "TD-PRICES": SecuritiesSource(
        # The results page carries a fresh CSRF token each time and lists same-maturity securities in no
        # fixed order, so a re-fetch is "unchanged" when its date and rows are, in any order.
        _spec("TD-PRICES", TD_PRICES_URL, "FedInvest, prices for Treasury securities (HTML, by price date)",
              parsers.parse_td_prices, dedupe_view=parsers.td_prices_view,
              pulls=("FedInvest's buy, sell and end-of-day price per CUSIP for each business day. quote-svc reads "
                     'them: the end-of-day price is the golden price.')),
        kind="day", shape="observations", calendar="SIFMA-US", first_period="2000-01-03", form=True,
    ),
    "FD-AUCTIONS": SecuritiesSource(
        _spec("FD-AUCTIONS", FD_AUCTIONS_URL, "Fiscal Data, Treasury securities auctions data (JSON, by month of auction)",
              parsers.parse_fd_auctions,
              pulls=("Fiscal Data's copy of the same auction records. A cross-check only: compared with "
                     "TreasuryDirect's each evening, nothing reads it otherwise.")),
        kind="month", shape="records", calendar="SIFMA-US", first_period="1979-01", ahead=1,
    ),
    "FD-MSPD-STRIPS": SecuritiesSource(
        _spec("FD-MSPD-STRIPS", FD_MSPD_STRIPS_URL,
              "Fiscal Data, Monthly Statement of the Public Debt, securities held in stripped form (JSON, by month)",
              parsers.parse_fd_mspd_strips,
              pulls=("The Monthly Statement of the Public Debt's STRIPS table: each security's amounts outstanding, "
                     'stripped and reconstituted. secmaster-svc reads them for its STRIPS.')),
        kind="month", shape="records", calendar="SIFMA-US", first_period="1985-01",
    ),
    "BLS-CPI": SecuritiesSource(
        _spec("BLS-CPI", BLS_CPI_URL, "BLS, CPI-U all items, not seasonally adjusted, CUUR0000SA0 (JSON, by year)",
              parsers.parse_bls_cpi, dedupe_view=bls_view,
              pulls=('CPI-U, all items, not seasonally adjusted, monthly. secmaster-svc reads it for the TIPS '
                     'reference CPIs and index ratios.')),
        kind="year", shape="observations", calendar="FED", first_period="1913", fetch=fetch_bls,
    ),
}


class BadPeriod(ValueError):
    pass


def current_period(kind: Kind, now: datetime | None = None) -> str:
    today = (now or datetime.now(EASTERN)).date()
    return {"day": today.isoformat(), "month": f"{today:%Y-%m}", "year": f"{today:%Y}"}[kind]


def _shift(kind: Kind, period: str, n: int) -> str:
    if kind == "day":
        return (date.fromisoformat(period) + timedelta(days=n)).isoformat()
    if kind == "year":
        return str(int(period) + n)
    y, m = (int(x) for x in period.split("-"))
    k = y * 12 + m - 1 + n
    return f"{k // 12:04d}-{k % 12 + 1:02d}"


def check_period(name: str, period: str, now: datetime | None = None, sources: dict | None = None) -> str:
    src = (sources or SOURCES)[name]
    try:
        if src.kind == "day":
            norm = date.fromisoformat(period).isoformat()
        elif src.kind == "year":
            norm = f"{int(period):04d}"
        else:
            y, m = (int(x) for x in period.split("-"))
            if not 1 <= m <= 12:
                raise ValueError
            norm = f"{y:04d}-{m:02d}"
        if norm != period:
            raise ValueError
    except ValueError:
        fmt = {"day": "YYYY-MM-DD", "month": "YYYY-MM", "year": "YYYY"}[src.kind]
        raise BadPeriod(f"{name}'s period is {fmt}, not {period!r}") from None
    latest = _shift(src.kind, current_period(src.kind, now), src.ahead)
    if not src.first_period <= period <= latest:
        raise BadPeriod(f"{name} serves {src.first_period} to {latest}, not {period}")
    return period


def post_fedinvest(period: str):
    """A fetcher for one FedInvest price date: read the form (session cookie and CSRF token), then post it."""
    date.fromisoformat(period)  # checked already; a bad one shouldn't reach the network

    def fetch(url: str) -> tuple[int, str | None, bytes]:
        headers = {"User-Agent": service.USER_AGENT}
        try:
            with httpx2.Client(timeout=service.FETCH_TIMEOUT_SECONDS, follow_redirects=True, headers=headers) as c:
                form = c.get(url)
                if form.status_code != 200:
                    raise SourceFetchError(f"{url} (form): HTTP {form.status_code}")
                m = CSRF.search(form.content)
                if m is None:
                    raise SourceFetchError(f"{url} (form): no CSRF token on the page")
                token = (m.group(1) or m.group(2)).decode()
                r = c.post(url, data={"priceDate": period, "submit": "Show Prices", "_csrf": token},
                           headers={"Referer": url})
        except httpx2.HTTPError as e:
            raise SourceFetchError(f"{url} ({period}): {e}") from None
        if r.status_code != 200:
            raise SourceFetchError(f"{url} ({period}): HTTP {r.status_code}")
        return r.status_code, r.headers.get("content-type"), r.content

    return fetch


def _apply_curve(s: Session, cap, parsed) -> dict:
    """Both halves of a curve file's parse: its observations, then its record (counts under "record")."""
    obs, recs = parsed
    out = near_raw.apply_period(s, cap, obs)
    return out | {"record": records.apply_period(s, cap, recs)}


def _apply(src: SecuritiesSource):
    if src.shape == "curve":
        return _apply_curve
    return records.apply_period if src.shape == "records" else near_raw.apply_period


def run_capture(s: Session, name: str, period: str, fetcher=None, sources: dict | None = None) -> dict:
    """Fetch one period of one source, keep it raw if new, and apply its parse to near-raw. Commits.

    As for the CMT sources: the raw capture is committed before parsing, so a
    parse error never loses what was fetched; the error is recorded on the
    check and raised (422). An unchanged fetch re-applies the same capture,
    which changes nothing. A source with no parser yet (`parse` None) is kept raw and stops there.

    `sources` is the registry the source is in: these, or phase 4's (app/futures/sources.py).
    """
    src = (sources or SOURCES)[name]
    period = check_period(name, period, sources=sources)
    if fetcher is None and src.form:
        fetcher = post_fedinvest(period)
    elif fetcher is None and src.fetch:
        fetcher = src.fetch
    cap, is_new, check = service.capture(s, src.spec, fetcher, url=src.url(period), period=period)
    s.commit()
    out = {"source": name, "period": period, "capture_id": cap.id, "new_capture": is_new,
           "size_bytes": cap.size_bytes, "content_type": cap.content_type}
    if src.spec.parse is None:
        return out | {"parsed": False}
    try:
        result = _apply(src)(s, cap, src.spec.parse(cap.body))
    except ParseError as e:  # raised before any row changes (apply_period checks first)
        check.parse_outcome, check.parse_detail = "error", str(e)[:2000]
        s.commit()
        raise
    check.parse_outcome = "ok"
    s.commit()
    return out | {"parsed": True} | result


def run_rebuild(s: Session, name: str, sources: dict | None = None) -> dict:
    """Rebuild one source's near-raw rows from every stored capture."""
    src = (sources or SOURCES)[name]
    service._source(s, src.spec)
    if src.shape == "curve":  # each half replayed on its own (each rebuild commits)
        out = near_raw.rebuild(s, name, lambda body: src.spec.parse(body)[0])
        return out | {"record": records.rebuild(s, name, lambda body: src.spec.parse(body)[1])}
    if src.shape == "records":
        return records.rebuild(s, name, src.spec.parse)
    return near_raw.rebuild(s, name, src.spec.parse)
