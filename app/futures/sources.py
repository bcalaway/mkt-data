"""Phase 4's sources (docs/phase-4.md, steps 1 and 4): captured raw; the fixings parsed (app/futures/parsers.py).

The fixings CME's rates and FX futures settle on or track, and the CFTC's
weekly positioning. As in phases 2 and 3, the raw history starts before any
parser, so the parsers are written against real bytes; the sandbox can't
reach these hosts, so the formats are read on the hub
(home-mcp's mkt_data_capture_text) from the first captures.

- NYFED-SOFR, NYFED-EFFR, NYFED-SOFR-AVG (month): the New York Fed's
  reference rates API, JSON, one month of effective dates per capture. SOFR
  with its percentiles and volume; EFFR with its percentiles, volume and the
  target range; the SOFR Averages (30, 90, 180-day) and the SOFR Index.
  Published each business day morning for the previous one.
- FRB-H10 (month): the Fed's H.10 daily dollar indexes (nominal broad,
  advanced foreign economies, emerging market economies; January 2006 on),
  the Data Download Program's "Daily Indexes" package, CSV. Published
  weekly, Mondays. (Meant to be the daily rates package; the series id
  turned out to be the indexes', which are worth keeping. The rates package
  is FRB-H10-RATES.)
- FRB-H10-RATES (month): the H.10 daily rates, every currency, the DDP's
  "Daily rates" package, CSV, January 1971 on. The DDP answers empty to a
  request that follows another within a second or so, so a fetch waits and
  asks again.
- ECB-EXR (month): the ECB's euro reference rates, every currency, daily, from
  the ECB data portal's SDMX API, CSV. Published each TARGET business day
  around 16:00 CET.
- CFTC-TFF and CFTC-TFF-COMBINED (day: the report's as-of date, a Tuesday):
  the CFTC's Traders in Financial Futures report, futures only and futures
  and options combined, every market, from its Public Reporting Environment
  (Socrata), CSV. Published Fridays at 3:30 p.m. Eastern, later after a
  federal holiday.

A period with nothing published yet answers empty (the New York Fed's `refRates: []`, the ECB's 404, a CSV
with only its header from the CFTC). That's a failed fetch with NOT_PUBLISHED in its message, nothing stored, so
an empty answer never becomes a capture; the capture DAG logs it quietly, like BLS's refusals.
"""

import json
import time

from app.calendars import service
from app.calendars.service import SourceFetchError, SourceSpec
from app.futures import parsers
from app.securities import sources as base
from app.securities.sources import SecuritiesSource

NOT_PUBLISHED = "NOT_PUBLISHED"

NYFED = "https://markets.newyorkfed.org/api/rates"
NYFED_SOFR_URL = NYFED + "/secured/sofr/search.json?startDate={first}&endDate={last}"
NYFED_EFFR_URL = NYFED + "/unsecured/effr/search.json?startDate={first}&endDate={last}"
NYFED_SOFR_AVG_URL = NYFED + "/secured/sofrai/search.json?startDate={first}&endDate={last}"
# The DDP's preformatted "H.10 Statistical Release - Daily Indexes" package (JRXWTFB_N.B, JRXWTFN_N.B, JRXWTFO_N.B;
# checked on the first captures, 2026-10-08), a month at a time.
FRB_H10_URL = (
    "https://www.federalreserve.gov/datadownload/Output.aspx?rel=H10&series=122e3bcb627e8e53f1bf72a1a09cfb81"
    "&lastobs=&from={first_us}&to={last_us}&filetype=csv&label=include&layout=seriescolumn"
)
# The DDP's preformatted "H.10 Statistical Release - Daily rates" package (Bill read its id off the DDP page,
# 2026-10-08), a month at a time.
FRB_H10_RATES_URL = (
    "https://www.federalreserve.gov/datadownload/Output.aspx?rel=H10&series=60f32914ab61dfab590e0e470153e3ae"
    "&lastobs=&from={first_us}&to={last_us}&filetype=csv&label=include&layout=seriescolumn"
)
# EXR, daily (D), every currency (blank), against the euro, spot (SP00), average (A): the reference rates.
ECB_EXR_URL = (
    "https://data-api.ecb.europa.eu/service/data/EXR/D..EUR.SP00.A"
    "?startPeriod={first}&endPeriod={last}&format=csvdata"
)
# Socrata: one report date's rows, every market, in market-code order (so a re-fetch is byte-identical).
CFTC = "https://publicreporting.cftc.gov/resource/"
CFTC_QUERY = (
    ".csv?%24where=report_date_as_yyyy_mm_dd%3D%27{first}T00%3A00%3A00.000%27"
    "&%24order=cftc_contract_market_code%2Cfutonly_or_combined&%24limit=50000"
)
CFTC_TFF_URL = CFTC + "gpe5-46if" + CFTC_QUERY  # TFF, futures only
CFTC_TFF_COMBINED_URL = CFTC + "yw9f-hn96" + CFTC_QUERY  # TFF, futures and options combined


def _not_published(url: str, why: str) -> SourceFetchError:
    return SourceFetchError(f"{url}: {NOT_PUBLISHED}: {why}")


def fetch_nyfed(url: str) -> tuple[int, str | None, bytes]:
    status, ctype, body = service.fetch(url)
    try:
        doc = json.loads(body)
    except ValueError:
        return status, ctype, body  # not JSON: kept, and the parser will say what's wrong with it
    if isinstance(doc, dict) and doc.get("refRates") == []:
        raise _not_published(url, "no rates for these dates yet")
    return status, ctype, body


DDP_TRIES = 3
DDP_PAUSE_SECONDS = 5


def fetch_ddp(url: str, sleep=time.sleep) -> tuple[int, str | None, bytes]:
    """The Fed's Data Download Program answers 200 with nothing in it when asked again too soon (every other request
    of the probe's run, 2026-10-08): wait and ask again, a few times, before calling it a failed fetch."""
    for attempt in range(DDP_TRIES):
        status, ctype, body = service.fetch(url)
        if body:
            return status, ctype, body
        if attempt < DDP_TRIES - 1:
            sleep(DDP_PAUSE_SECONDS)
    raise SourceFetchError(f"{url}: empty response, {DDP_TRIES} tries")


def fetch_ecb(url: str) -> tuple[int, str | None, bytes]:
    try:
        return service.fetch(url)
    except SourceFetchError as e:
        if "HTTP 404" in str(e):  # the ECB's answer for a query with no data
            raise _not_published(url, "no reference rates for these dates yet") from None
        raise


def fetch_cftc(url: str) -> tuple[int, str | None, bytes]:
    status, ctype, body = service.fetch(url)
    if len([line for line in body.splitlines() if line.strip()]) <= 1:
        raise _not_published(url, "no report for this date (yet)")
    return status, ctype, body


def _source(name, url, description, pulls, kind, calendar, first_period, fetch, parse=None) -> SecuritiesSource:
    spec = SourceSpec(name, url, description, parse, pulls=pulls)
    return SecuritiesSource(spec, kind=kind, shape="observations", calendar=calendar, first_period=first_period,
                            fetch=fetch)


KEPT_RAW = "Kept raw for now (phase 4, step 1): quote-svc reads it once it has a parser."
PARSED = "Parsed to near-raw observations as published (phase 4, step 4); quote-svc builds the fixings from them."

SOURCES: dict[str, SecuritiesSource] = {
    "NYFED-SOFR": _source(
        "NYFED-SOFR", NYFED_SOFR_URL, "New York Fed reference rates API, SOFR (JSON, by month)",
        f"SOFR each business day, with its percentiles and volume: what one- and three-month SOFR futures settle on. "
        f"{PARSED}", "month", "SIFMA-US", "2018-04", fetch_nyfed, parsers.parse_sofr),
    "NYFED-EFFR": _source(
        "NYFED-EFFR", NYFED_EFFR_URL, "New York Fed reference rates API, EFFR (JSON, by month)",
        f"The effective Fed funds rate each business day, with its percentiles, volume and the FOMC's target range: "
        f"what Fed funds futures settle on. {PARSED}", "month", "FED", "2000-01", fetch_nyfed, parsers.parse_effr),
    "NYFED-SOFR-AVG": _source(
        "NYFED-SOFR-AVG", NYFED_SOFR_AVG_URL, "New York Fed reference rates API, SOFR Averages and Index (JSON, by month)",
        "The 30-, 90- and 180-day SOFR Averages and the SOFR Index each business day. Kept raw, nothing reads it "
        "yet: averaging is analytics, for a later phase (Bill, 2026-10-09), when quote-svc may read it.",
        "month", "SIFMA-US", "2020-03", fetch_nyfed),
    "FRB-H10": _source(
        "FRB-H10", FRB_H10_URL, "Federal Reserve H.10, nominal dollar indexes, daily (CSV, by month)",
        f"The Fed's daily nominal dollar indexes: broad, advanced foreign economies and emerging market economies. "
        f"{PARSED}", "month", "FED", "2006-01", fetch_ddp, parsers.parse_ddp),
    "FRB-H10-RATES": _source(
        "FRB-H10-RATES", FRB_H10_RATES_URL, "Federal Reserve H.10, foreign exchange rates, daily (CSV, by month)",
        f"The Fed's daily noon buying rates in New York for each currency, as H.10 quotes them: what CME's FX futures "
        f"track. {PARSED}", "month", "FED", "1971-01", fetch_ddp, parsers.parse_ddp),
    "ECB-EXR": _source(
        "ECB-EXR", ECB_EXR_URL, "ECB euro foreign exchange reference rates, daily (CSV, by month)",
        f"The ECB's euro reference rate for each currency, each TARGET business day. {PARSED}",
        "month", "TARGET", "1999-01", fetch_ecb, parsers.parse_ecb),
    "CFTC-TFF": _source(
        "CFTC-TFF", CFTC_TFF_URL, "CFTC Traders in Financial Futures, futures only (CSV, by report date)",
        f"Positions by trader category (dealers, asset managers, leveraged funds, other reportables, non-reportables) "
        f"in every financial futures market, weekly as of Tuesday. {KEPT_RAW}",
        "day", "FED", "2006-06-13", fetch_cftc),
    "CFTC-TFF-COMBINED": _source(
        "CFTC-TFF-COMBINED", CFTC_TFF_COMBINED_URL,
        "CFTC Traders in Financial Futures, futures and options combined (CSV, by report date)",
        f"The same report with options on futures included, delta-adjusted. {KEPT_RAW}",
        "day", "FED", "2006-06-13", fetch_cftc),
}


def run_capture(s, name: str, period: str, fetcher=None) -> dict:
    return base.run_capture(s, name, period, fetcher, sources=SOURCES)


def check_period(name: str, period: str, now=None) -> str:
    return base.check_period(name, period, now, sources=SOURCES)
