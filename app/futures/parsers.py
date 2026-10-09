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
