"""Parsers for phase 4's fixings (docs/phase-4.md, step 4): near-raw observations, as published.

Each returns the observations in one capture (one month), as the source prints them: its own series key,
the date, the field and the value (a Decimal of the printed digits). No conversion and no mapping to
instruments: secmaster-svc names the instruments and quote-svc builds the quotes. A page that doesn't look
like the source's format is a ParseError, and the raw capture is kept for a fixed parser.

- NYFED-SOFR, NYFED-EFFR: the New York Fed's JSON. Key `SOFR` / `EFFR`; one observation per number the
  record carries, under the API's own field name (`percentRate`, `percentPercentile25`, `volumeInBillions`,
  `targetRateFrom`, ...), in percent (or USD billions for the volume).
- FRB-H10, FRB-H10-RATES: the Fed's Data Download Program CSV. Key the DDP series (`RXI$US_N.B.EU`: dollars
  per euro; `RXI_N.B.JA`: yen per dollar; `JRXWTFB_N.B`: the broad dollar index), field `value`, unit from
  the header's Unit and Currency rows. `ND` (no data: a holiday) is skipped.
- ECB-EXR: the ECB data portal's SDMX CSV. Key the series (`EXR.D.JPY.EUR.SP00.A`), field `rate`, unit
  `JPY per EUR`.

- CFTC-TFF, CFTC-TFF-COMBINED: the CFTC's Traders in Financial Futures report (Socrata CSV, one report
  date, every market). Key the contract market code (`043602`: 10-year T-note futures), field the CFTC's
  column name, for the published levels only: open interest, each trader category's long, short and
  spreading positions (`unit` contracts), the number of traders in each (`traders`), and the
  concentration ratios (`percent`). The week-on-week changes and the percents of open interest are
  arithmetic on those, so they stay in the raw capture. A count the CFTC leaves empty (it withholds
  categories with too few traders) is skipped.

The SOFR Averages and Index (NYFED-SOFR-AVG) stay raw: averaging is analytics, for a later phase (Bill,
2026-10-09).
"""

import csv
import io
import json
import re
from datetime import date
from decimal import Decimal, InvalidOperation

from app.calendars.parsed import ParseError
from app.rates.parsers import Obs

NYFED_SKIP = {"effectiveDate", "type", "revisionIndicator", "footnoteId", "footnote"}
NYFED_NA = {"NA", "N/A"}
DDP_SERIES = re.compile(r"^[A-Z0-9$_.]+$")


def _decimal(v, where: str) -> Decimal:
    try:
        d = v if isinstance(v, Decimal) else Decimal(str(v).strip())
    except InvalidOperation:
        raise ParseError(f"{where}: {v!r} isn't a number") from None
    if not d.is_finite():
        raise ParseError(f"{where}: {v!r} isn't a number")
    return d


def _date(text: str, where: str) -> date:
    try:
        return date.fromisoformat(str(text).strip()[:10])
    except ValueError:
        raise ParseError(f"{where}: bad date {text!r}") from None


def parse_nyfed(content: bytes, kind: str) -> list[Obs]:
    """One month of SOFR or EFFR. Numbers are read as printed (JSON floats as Decimals)."""
    try:
        doc = json.loads(content, parse_float=Decimal, parse_int=Decimal)
    except ValueError:
        raise ParseError("not JSON") from None
    rates = doc.get("refRates") if isinstance(doc, dict) else None
    if not isinstance(rates, list):
        raise ParseError("no refRates list")
    out = []
    for r in rates:
        if not isinstance(r, dict) or r.get("type") != kind:
            raise ParseError(f"expected {kind} records, got {str(r)[:80]}")
        day = _date(r.get("effectiveDate", ""), kind)
        for field, v in r.items():
            if field in NYFED_SKIP or v is None or v == "" or v in NYFED_NA:
                continue  # "NA": not available that day (SOFR's 1st percentile on 2019-05-31, 2021-08-05)
            if not isinstance(v, Decimal):
                raise ParseError(f"{day} {field}: {v!r} isn't a number")
            unit = "USD billions" if field.startswith("volume") else "percent"
            out.append(Obs(kind, day, _decimal(v, f"{day} {field}"), field=field[:20], unit=unit))
    return out


def parse_sofr(content: bytes) -> list[Obs]:
    return parse_nyfed(content, "SOFR")


def parse_effr(content: bytes) -> list[Obs]:
    return parse_nyfed(content, "EFFR")


def parse_ddp(content: bytes) -> list[Obs]:
    """The DDP's series-in-columns CSV: header rows, then `Time Period` and one row per day."""
    try:
        text = content.decode("utf-8-sig")
    except UnicodeDecodeError:
        raise ParseError("not UTF-8 text") from None
    rows = list(csv.reader(io.StringIO(text)))
    header = next((i for i, r in enumerate(rows) if r and r[0].strip() == "Time Period"), None)
    if header is None:
        raise ParseError("no 'Time Period' header row")
    series = [c.strip() for c in rows[header][1:]]
    if not series or not all(DDP_SERIES.match(s) for s in series):
        raise ParseError(f"unexpected series in the header: {series}")
    meta = {r[0].strip().rstrip(":").strip(): [c.strip() for c in r[1:]] for r in rows[:header] if r}
    units = []
    for i in range(len(series)):
        unit = (meta.get("Unit") or [""] * len(series))[i]
        cur = (meta.get("Currency") or [""] * len(series))[i]
        if unit.lower().startswith("index"):
            units.append("index")
        elif cur and cur not in ("NA", ""):
            units.append(f"{cur} currency"[:20])
        else:
            units.append((unit or "value")[:20])
    out = []
    for r in rows[header + 1:]:
        if not r or not r[0].strip():
            continue
        day = _date(r[0], "DDP")
        if len(r) - 1 != len(series):
            raise ParseError(f"{day}: {len(r) - 1} values for {len(series)} series")
        for key, unit, cell in zip(series, units, r[1:], strict=True):
            cell = cell.strip()
            if cell in ("", "ND", "NA", "NC"):  # no data: a holiday, or not published
                continue
            out.append(Obs(key, day, _decimal(cell, f"{day} {key}"), field="value", unit=unit))
    return out


def parse_ecb(content: bytes) -> list[Obs]:
    """The ECB's SDMX CSV for EXR: one row per series and day."""
    try:
        text = content.decode("utf-8-sig")
    except UnicodeDecodeError:
        raise ParseError("not UTF-8 text") from None
    reader = csv.DictReader(io.StringIO(text))
    need = {"KEY", "CURRENCY", "CURRENCY_DENOM", "TIME_PERIOD", "OBS_VALUE"}
    if not reader.fieldnames or not need <= set(reader.fieldnames):
        raise ParseError(f"missing columns {sorted(need - set(reader.fieldnames or []))}")
    out = []
    for r in reader:
        value = (r["OBS_VALUE"] or "").strip()
        if value in ("", "NaN"):
            continue
        day = _date(r["TIME_PERIOD"], r["KEY"])
        out.append(Obs(r["KEY"].strip(), day, _decimal(value, f"{day} {r['KEY']}"), field="rate",
                       unit=f"{r['CURRENCY'].strip()} per {r['CURRENCY_DENOM'].strip()}"[:20]))
    return out


CFTC_LEVELS = ("open_interest_all", "dealer_positions_", "asset_mgr_positions_", "lev_money_positions_",
               "other_rept_positions_", "tot_rept_positions_", "nonrept_positions_", "traders_", "conc_")
CFTC_NEED = {"id", "report_date_as_yyyy_mm_dd", "cftc_contract_market_code", "open_interest_all"}
CFTC_CODE = re.compile(r"^[0-9A-Z]{5}[0-9A-Z+]$")


def _cftc_unit(column: str) -> str:
    if column.startswith("traders_"):
        return "traders"
    if column.startswith("conc_"):
        return "percent"
    return "contracts"


def parse_cftc(content: bytes, kind: str) -> list[Obs]:
    """One TFF report date, every market. kind: F (futures only) or C (futures and options combined), the
    last letter of each row's id."""
    try:
        text = content.decode("utf-8-sig")
    except UnicodeDecodeError:
        raise ParseError("not UTF-8 text") from None
    reader = csv.DictReader(io.StringIO(text))
    if not reader.fieldnames or not CFTC_NEED <= set(reader.fieldnames):
        raise ParseError(f"missing columns {sorted(CFTC_NEED - set(reader.fieldnames or []))}")
    columns = [c for c in reader.fieldnames if c.startswith(CFTC_LEVELS)]
    out, days, seen = [], set(), set()
    for r in reader:
        code = (r["cftc_contract_market_code"] or "").strip()
        if not CFTC_CODE.match(code):
            raise ParseError(f"unexpected contract market code {code!r}")
        if not r["id"].strip().endswith(kind):
            raise ParseError(f"{code}: row {r['id']!r} isn't a {'futures-only' if kind == 'F' else 'combined'} row")
        if code in seen:
            raise ParseError(f"{code} twice in one report")
        seen.add(code)
        day = _date(r["report_date_as_yyyy_mm_dd"], code)
        days.add(day)
        for c in columns:
            v = (r[c] or "").strip()
            if v in ("", "."):
                continue  # withheld: too few traders in the category
            out.append(Obs(code, day, _decimal(v, f"{day} {code} {c}"), field=c, unit=_cftc_unit(c)))
    if len(days) > 1:
        raise ParseError(f"more than one report date: {sorted(days)}")
    return out


def parse_tff(content: bytes) -> list[Obs]:
    return parse_cftc(content, "F")


def parse_tff_combined(content: bytes) -> list[Obs]:
    return parse_cftc(content, "C")
