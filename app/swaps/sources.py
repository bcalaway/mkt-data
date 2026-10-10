"""The ISDA standard model's RFR swap curves, from S&P Global Market Intelligence (docs/phase-4.md, "Swap curves").

S&P Global Market Intelligence (SPGMI) is the administrator of the risk-free-rate OIS curves that feed ISDA's CDS
Standard Model (cdsmodel.com): one file per currency per weekday, published at https://rfr.spglobal.com. Facts here
are from the SPGMI Interest Rate Curve XML Specification (RFRs), v1.3, 2026-06-15 (sections cited); the document
itself is confidential and isn't kept in this repo.

- Six currencies (section 5.2): USD (SOFR), EUR (€STR), GBP (SONIA), JPY (TONA), CHF (SARON), AUD (AONIA). One source
  each, SPGMI-RFR-<CCY>, since each has its own close and publication time.
- A period is a publication date (YYYY-MM-DD), the file's name's date: InterestRates_<CCY>_<yyyymmdd>.zip (5.1). The
  file is for trade date T and published on T-1 weekday (5.5).
- Published every weekday, holidays included, never at weekends (5.3). On a holiday with no new rates SPGMI repeats
  the latest curve. Snapped at 16:00 local to the currency's reference city (New York, Frankfurt, London, Tokyo,
  Zurich, Sydney), usually out at 16:50, due by 17:30 (5.2).
- The download needs an email address whose owner has accepted S&P's terms at https://rfr.spglobal.com in the last
  year (5.4.1), passed as `?email=`. It arrives as SPGMI_RFR_EMAIL from SSM (/home-platform/mkt-data/spgmi-rfr-email)
  and is added by the fetch, so it's never in a stored URL or an error message.
- What S&P answers instead of a file (5.4.2): "Interest Rates not available, please check date and/or currency
  entered" (not published yet, a weekend, a bad date) is NOT_PUBLISHED, nothing stored; "Username not known" or
  "Accept/re-accept terms of use" means the terms need accepting again.

Each capture is the zip as downloaded; its XML is parsed (app/swaps/parsers.py) into near-raw observations (each
tenor's par rate) and one `curve` record (conventions, spot date, maturity dates, as printed).
"""

from urllib.parse import quote

import httpx2

from app import config
from app.calendars import service
from app.calendars.service import SourceFetchError, SourceSpec
from app.securities import sources as base
from app.securities.sources import SecuritiesSource
from app.swaps import parsers

NOT_PUBLISHED = "NOT_PUBLISHED"
TERMS = "TERMS_NOT_ACCEPTED"
SITE = "https://rfr.spglobal.com"
URL = SITE + "/InterestRates_{ccy}_{ymd}.zip"
SSM_EMAIL = "/home-platform/mkt-data/spgmi-rfr-email"

# currency: (overnight rate, reference city, publication calendar for labels (calendar-svc), first period to ask for)
# The RFR curves began with GBP (ISDA's announcement, 2021-02-11; the spec's v1.0 is 2021-04-07) and the others in
# March 2022 (section 1.1). How far back the site serves is for the backfill to find.
CURRENCIES = {
    "USD": ("SOFR", "New York", "FED", "2021-04-01"),
    "EUR": ("€STR", "Frankfurt", "TARGET", "2021-04-01"),
    "GBP": ("SONIA", "London", "GB", "2021-02-01"),
    "JPY": ("TONA", "Tokyo", "JP", "2021-04-01"),
    "CHF": ("SARON", "Zurich", "CH", "2021-04-01"),
    "AUD": ("AONIA", "Sydney", "AU", "2021-04-01"),
}


def _email() -> str:
    email = (config.settings.spgmi_rfr_email or "").strip()
    if not email:
        raise SourceFetchError(f"SPGMI_RFR_EMAIL isn't set: put the address that accepted S&P's terms in SSM "
                               f"{SSM_EMAIL} and redeploy mkt-data")
    return email


def _get(url: str) -> tuple[int, str | None, bytes]:
    """A GET that returns error answers too (S&P explains a refusal in the body)."""
    try:
        r = httpx2.get(url, timeout=service.FETCH_TIMEOUT_SECONDS, follow_redirects=True,
                       headers={"User-Agent": service.USER_AGENT})
    except httpx2.HTTPError as e:
        raise SourceFetchError(str(e)) from None
    return r.status_code, r.headers.get("content-type"), r.content


def _scrub(text: str, email: str) -> str:
    """The text without the email, as typed or URL-encoded: rfr.spglobal.com redirects (302) to its API host,
    pvr-rfr-api.api.rfr.spglobal.com, with the address re-encoded (%40), and an HTTP error names that URL."""
    return text.replace(email, "<email>").replace(quote(email, safe=""), "<email>")


def fetch_spgmi(url: str) -> tuple[int, str | None, bytes]:
    """Fetch one file with the registered email added, and turn S&P's refusals into failed fetches.

    `url` is the stored one, without the email; every error names it, never the email.
    """
    email = _email()
    try:
        status, ctype, body = _get(f"{url}?email={email}")
    except SourceFetchError as e:
        raise SourceFetchError(f"{url}: {_scrub(str(e), email)}") from None
    if status == 200 and (body[:2] == b"PK" or body.lstrip()[:1] == b"<" and b"interestRateCurve" in body[:4000]):
        return status, ctype, body
    message = " ".join(_scrub(body[:600].decode("utf-8", errors="replace"), email).split())
    low = message.lower()
    if "not available" in low:
        raise SourceFetchError(f"{url}: {NOT_PUBLISHED}: {message[:200]}")
    if "terms of use" in low or "username not known" in low:
        raise SourceFetchError(f"{url}: {TERMS}: {message[:200]} (accept S&P's terms at {SITE} with the address in "
                               f"SSM {SSM_EMAIL})")
    raise SourceFetchError(f"{url}: HTTP {status}, not a curve file: {message[:300]}")


def _source(ccy: str) -> SecuritiesSource:
    rate, city, calendar, first = CURRENCIES[ccy]
    name = f"SPGMI-RFR-{ccy}"
    spec = SourceSpec(
        name, URL.replace("{ccy}", ccy),
        f"S&P Global Market Intelligence, ISDA standard model RFR curve, {ccy} {rate} OIS (zipped XML, by "
        f"publication date)",
        parsers.make_parser(ccy), dedupe_view=parsers.curve_view,
        pulls=(f"The {ccy} {rate} OIS par swap curve ISDA's CDS Standard Model uses, snapped at 16:00 {city} each "
               f"weekday: each tenor's par rate, with the file's conventions, spot date and maturity dates. Parsed to "
               f"near-raw observations and a curve record; secmaster-svc checks the {ccy} OIS swaps' conventions "
               f"against it."),
    )
    return SecuritiesSource(spec, kind="day", shape="curve", calendar=calendar, first_period=first, fetch=fetch_spgmi)


SOURCES: dict[str, SecuritiesSource] = {f"SPGMI-RFR-{ccy}": _source(ccy) for ccy in CURRENCIES}


def run_capture(s, name: str, period: str, fetcher=None) -> dict:
    return base.run_capture(s, name, period, fetcher, sources=SOURCES)


def run_rebuild(s, name: str) -> dict:
    return base.run_rebuild(s, name, sources=SOURCES)


def check_period(name: str, period: str, now=None) -> str:
    return base.check_period(name, period, now, sources=SOURCES)
