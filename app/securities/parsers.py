"""Parsers for the Treasury securities sources (docs/phase-3.md, step 2): near-raw, as published.

Two shapes come out:

- **Records** (`Rec`) for what isn't a time series: an auction's terms and
  results (TD-SECURITIES, FD-AUCTIONS) and a month-end line of the stripped-
  securities table (FD-MSPD-STRIPS). A record keeps the source's own field
  names and values exactly as printed (strings, the source's own blanks: ""
  for TreasuryDirect, "null" for Fiscal Data); nothing is typed or renamed
  here. secmaster-svc types them.
- **Observations** (`Obs`, the phase 2 table) for time series: FedInvest's
  buy, sell and end-of-day prices per CUSIP (TD-PRICES) and the CPI-U index
  (BLS-CPI), values as printed.

A period with nothing in it parses to nothing (a month before a source's
history, a price date FedInvest has no prices for); anything that doesn't
look like the source's format is a ParseError, and the raw capture stays for
a fixed parser.
"""

import json
from dataclasses import dataclass, field
from datetime import date, datetime
from decimal import Decimal
from html.parser import HTMLParser

from app.calendars.parsed import ParseError
from app.rates.parsers import Obs, _decimal

PRICE_UNIT = "per_100"  # FedInvest prices: decimal, per 100 of face
PRICE_FIELDS = ("buy", "sell", "eod")
CPI_UNIT = "index"  # CPI-U, 1982-84 = 100


@dataclass(frozen=True)
class Rec:
    record_type: str  # "auction", "stripped_security"
    source_key: str  # unique within the source and type: "912810UW6/2026-10-15"
    as_of: date  # the date that places it in a capture's period (auction date, record date)
    fields: dict = field(compare=False, hash=False)  # as published


def _json(body: bytes, what: str):
    try:
        return json.loads(body)
    except (UnicodeDecodeError, json.JSONDecodeError) as e:
        raise ParseError(f"{what}: not JSON ({e})") from None


def _day(text, where: str) -> date:
    """A date printed as YYYY-MM-DD, optionally with a time (TreasuryDirect's ...T00:00:00)."""
    if not isinstance(text, str) or len(text) < 10:
        raise ParseError(f"{where}: {text!r} isn't a date")
    try:
        return date.fromisoformat(text[:10])
    except ValueError:
        raise ParseError(f"{where}: {text!r} isn't a date") from None


def _unique(recs: list[Rec], what: str) -> list[Rec]:
    """Drop exact repeats; two different records under one key is a ParseError."""
    seen: dict[tuple, Rec] = {}
    for r in recs:
        k = (r.record_type, r.source_key)
        if k in seen:
            if seen[k].fields != r.fields:
                raise ParseError(f"{what}: two different records for {r.source_key}")
            continue
        seen[k] = r
    return list(seen.values())


# --- TD-SECURITIES: TreasuryDirect's securities web API (JSON list) --------


def parse_td_securities(body: bytes) -> list[Rec]:
    """One record per security and auction, keyed CUSIP/issue date (a reopening has its own issue date)."""
    doc = _json(body, "TD-SECURITIES")
    if not isinstance(doc, list):
        raise ParseError("TD-SECURITIES: expected a JSON list of securities")
    recs = []
    for i, row in enumerate(doc):
        if not isinstance(row, dict) or not row.get("cusip"):
            raise ParseError(f"TD-SECURITIES: entry {i} has no cusip")
        issue = _day(row.get("issueDate"), f"TD-SECURITIES {row['cusip']} issueDate")
        auction = _day(row.get("auctionDate"), f"TD-SECURITIES {row['cusip']} auctionDate")
        recs.append(Rec("auction", f"{row['cusip']}/{issue.isoformat()}", auction, row))
    return _unique(recs, "TD-SECURITIES")


# --- Fiscal Data (FD-AUCTIONS, FD-MSPD-STRIPS): {"data": [...], "meta": {...}} --


def _fiscal_data(body: bytes, what: str) -> list[dict]:
    doc = _json(body, what)
    if not isinstance(doc, dict) or not isinstance(doc.get("data"), list):
        raise ParseError(f"{what}: expected Fiscal Data's {{data, meta}}")
    pages = (doc.get("meta") or {}).get("total-pages")
    if pages not in (None, 0, 1):
        raise ParseError(f"{what}: {pages} pages; the capture holds only the first")
    return doc["data"]


def parse_fd_auctions(body: bytes) -> list[Rec]:
    recs = []
    for i, row in enumerate(_fiscal_data(body, "FD-AUCTIONS")):
        if not isinstance(row, dict) or not row.get("cusip"):
            raise ParseError(f"FD-AUCTIONS: entry {i} has no cusip")
        issue = _day(row.get("issue_date"), f"FD-AUCTIONS {row['cusip']} issue_date")
        auction = _day(row.get("auction_date"), f"FD-AUCTIONS {row['cusip']} auction_date")
        recs.append(Rec("auction", f"{row['cusip']}/{issue.isoformat()}", auction, row))
    return _unique(recs, "FD-AUCTIONS")


def parse_fd_mspd_strips(body: bytes) -> list[Rec]:
    """One record per principal STRIPS CUSIP and month-end, keyed CUSIP/record date.

    The table's subtotal and grand-total lines (cusip "null": "Total Treasury
    Notes", ..., "Grand Total") are kept too, as `stripped_total` records keyed
    by their label, so the per-security lines can be checked against them.
    """
    recs = []
    for i, row in enumerate(_fiscal_data(body, "FD-MSPD-STRIPS")):
        if not isinstance(row, dict) or not row.get("cusip"):
            raise ParseError(f"FD-MSPD-STRIPS: entry {i} has no cusip")
        on = _day(row.get("record_date"), f"FD-MSPD-STRIPS line {i} record_date")
        if row["cusip"] == "null":
            label = row.get("security_class2_desc")
            label = row.get("security_class1_desc") if label in (None, "null") else label
            if not label or label == "null":
                raise ParseError(f"FD-MSPD-STRIPS: line {i} has neither a cusip nor a label")
            recs.append(Rec("stripped_total", f"{label}/{on.isoformat()}", on, row))
        else:
            recs.append(Rec("stripped_security", f"{row['cusip']}/{on.isoformat()}", on, row))
    return _unique(recs, "FD-MSPD-STRIPS")


# --- TD-PRICES: FedInvest's Historical Prices page (HTML table) -------------

PRICE_HEADER = ["CUSIP", "SECURITY TYPE", "RATE", "MATURITY DATE", "CALL DATE", "BUY", "SELL", "END OF DAY"]


class _PricePage(HTMLParser):
    """Collects the "Prices For: <date>" heading and the data1 table's rows (cells as text)."""

    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.heading: list[str] = []
        self.rows: list[list[str]] = []
        self.tables = 0
        self._in_h2 = self._in_table = False
        self._cell: list[str] | None = None
        self._row: list[str] | None = None

    def handle_starttag(self, tag, attrs):
        if tag == "h2":
            self._in_h2 = True
        elif tag == "table" and ("class", "data1") in attrs:
            self._in_table, self.tables = True, self.tables + 1
        elif self._in_table and tag == "tr":
            self._row = []
        elif self._in_table and tag in ("td", "th") and self._row is not None:
            self._cell = []

    def handle_endtag(self, tag):
        if tag == "h2":
            self._in_h2 = False
        elif tag == "table" and self._in_table:
            self._in_table = False
        elif tag in ("td", "th") and self._cell is not None and self._row is not None:
            self._row.append(" ".join("".join(self._cell).split()))
            self._cell = None
        elif tag == "tr" and self._row is not None:
            self.rows.append(self._row)
            self._row = None

    def handle_data(self, data):
        if self._in_h2:
            self.heading.append(data)
        if self._cell is not None:
            self._cell.append(data)


def parse_td_prices(body: bytes) -> list[Obs]:
    """Buy, sell and end-of-day price per CUSIP for the page's date; "0.000000" (not available) is no value."""
    page = _PricePage()
    page.feed(body.decode("latin-1"))
    heading = " ".join("".join(page.heading).split())
    if "Prices For:" not in heading:
        raise ParseError("TD-PRICES: no \"Prices For:\" heading; not a prices page")
    try:
        on = datetime.strptime(heading.split("Prices For:", 1)[1].strip(), "%B %d, %Y").date()  # noqa: DTZ007 (a date)
    except ValueError:
        raise ParseError(f"TD-PRICES: can't read the date in {heading!r}") from None
    if page.tables != 1 or not page.rows:
        raise ParseError(f"TD-PRICES: expected one prices table, found {page.tables}")
    if page.rows[0] != PRICE_HEADER:
        raise ParseError(f"TD-PRICES: unexpected columns {page.rows[0]}")
    obs: list[Obs] = []
    seen: dict[str, list[str]] = {}
    for row in page.rows[1:]:
        if len(row) != len(PRICE_HEADER):
            raise ParseError(f"TD-PRICES {on}: a row has {len(row)} cells: {row}")
        cusip = row[0]
        if len(cusip) != 9:
            raise ParseError(f"TD-PRICES {on}: {cusip!r} isn't a CUSIP")
        if cusip in seen:
            if seen[cusip] != row:
                raise ParseError(f"TD-PRICES {on}: two different rows for {cusip}")
            continue
        seen[cusip] = row
        for name, text in zip(PRICE_FIELDS, row[5:], strict=True):
            value = _decimal(text, f"TD-PRICES {on} {cusip} {name}")
            if value != 0:
                obs.append(Obs(cusip, on, value, field=name, unit=PRICE_UNIT))
    return obs


# --- BLS-CPI: BLS public data API v2 (JSON) ---------------------------------


def parse_bls_cpi(body: bytes) -> list[Obs]:
    """Monthly index values, dated the first of their month. The annual average (M13) is left out."""
    doc = _json(body, "BLS-CPI")
    if not isinstance(doc, dict) or doc.get("status") != "REQUEST_SUCCEEDED":
        status = doc.get("status") if isinstance(doc, dict) else None
        raise ParseError(f"BLS-CPI: request not processed (status {status!r}): {str(doc)[:300]}")
    try:
        series = doc["Results"]["series"]
    except (KeyError, TypeError):
        raise ParseError("BLS-CPI: no Results.series") from None
    obs = []
    for s in series:
        key = s.get("seriesID")
        for row in s.get("data", []):
            period = row.get("period", "")
            if period == "M13":
                continue
            if not (period.startswith("M") and period[1:].isdigit() and 1 <= int(period[1:]) <= 12):
                raise ParseError(f"BLS-CPI {key}: unexpected period {period!r}")
            try:
                on = date(int(row["year"]), int(period[1:]), 1)
            except (KeyError, ValueError):
                raise ParseError(f"BLS-CPI {key}: bad year in {row}") from None
            text = str(row.get("value", "")).strip()
            if text == "-":  # a month BLS never published (October 2025, the shutdown)
                continue
            value: Decimal = _decimal(text, f"BLS-CPI {key} {on:%Y-%m}")
            obs.append(Obs(key, on, value, field="index", unit=CPI_UNIT))
    return obs
