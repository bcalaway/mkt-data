"""Parsers for the Treasury CMT sources: near-raw observations, as published.

Each returns the observations in one capture (one month): the source's own
key for the series, the date, the field and the value exactly as printed
(a Decimal of the printed digits, in percent). No conversion, no mapping to
instruments: that's quote-svc's and secmaster-svc's job (docs/phase-2.md).
A month with no data yet (the first business day of a month, before Treasury
posts) parses to no observations; a page that doesn't look like the source's
format is a ParseError, and the raw capture is kept for a fixed parser.
"""

import csv
import io
import re
import xml.etree.ElementTree as ET
from dataclasses import dataclass
from datetime import date
from decimal import Decimal, InvalidOperation

from app.calendars.parsed import ParseError

FIELD = "yield"
UNIT = "percent"


@dataclass(frozen=True)
class Obs:
    source_key: str  # the source's own name for the series: BC_10YEAR, RIFLGFCY10_N.B
    as_of: date
    value: Decimal  # as printed, e.g. Decimal("4.06")
    field: str = FIELD
    unit: str = UNIT


def _decimal(text: str, where: str) -> Decimal:
    try:
        d = Decimal(text.strip())
    except InvalidOperation:
        raise ParseError(f"{where}: {text!r} isn't a number") from None
    if not d.is_finite():
        raise ParseError(f"{where}: {text!r} isn't a finite number")
    return d


# --- UST-PAR: Treasury's Daily Par Yield Curve Rates, OData/Atom XML -------

_ATOM = "{http://www.w3.org/2005/Atom}"
_M = "{http://schemas.microsoft.com/ado/2007/08/dataservices/metadata}"
_D = "{http://schemas.microsoft.com/ado/2007/08/dataservices}"
# Tenor elements: BC_1MONTH, BC_1_5MONTH, BC_10YEAR ... Treasury adds one now
# and then (BC_4MONTH in 2022, BC_1_5MONTH in 2025): any BC_<n>(_<n>)MONTH/YEAR
# is kept, so a new tenor needs no parser change. BC_30YEARDISPLAY (a display
# copy of BC_30YEAR) is skipped. A missing value is an omitted element.
_TENOR = re.compile(r"^BC_\d+(_\d+)?(MONTH|YEAR)$")


def parse_ust_par(content: bytes) -> list[Obs]:
    try:
        root = ET.fromstring(content)
    except ET.ParseError as e:
        raise ParseError(f"not XML: {e}") from None
    if root.tag != f"{_ATOM}feed":
        raise ParseError(f"expected an Atom feed, got <{root.tag}>")
    out, seen = [], set()
    for entry in root.iter(f"{_ATOM}entry"):
        props = entry.find(f"{_ATOM}content/{_M}properties")
        if props is None:
            raise ParseError("an entry has no m:properties")
        new_date = props.find(f"{_D}NEW_DATE")
        if new_date is None or not (new_date.text or "").strip():
            raise ParseError("an entry has no NEW_DATE")
        try:
            day = date.fromisoformat(new_date.text.strip()[:10])
        except ValueError:
            raise ParseError(f"bad NEW_DATE {new_date.text!r}") from None
        if day in seen:
            raise ParseError(f"{day} appears twice")
        seen.add(day)
        tenors = 0
        for el in props:
            key = el.tag.removeprefix(_D)
            if not _TENOR.match(key):
                continue
            if el.get(f"{_M}null") == "true" or not (el.text or "").strip():
                continue  # no value for that tenor that day
            out.append(Obs(key, day, _decimal(el.text, f"{day} {key}")))
            tenors += 1
        if tenors == 0:
            raise ParseError(f"{day} has no tenor values")
    return out


# --- H15-TCM: the Fed's H.15 Data Download Program CSV -----------------------

_SERIES = re.compile(r"^RIFLGFC[MY]\d{2}_N\.B$")


def parse_h15_tcm(content: bytes) -> list[Obs]:
    try:
        text = content.decode("utf-8-sig")
    except UnicodeDecodeError:
        raise ParseError("not UTF-8 text") from None
    rows = list(csv.reader(io.StringIO(text)))
    header = next((i for i, r in enumerate(rows) if r and r[0].strip() == "Time Period"), None)
    if header is None:
        raise ParseError("no 'Time Period' header row")
    series = [c.strip() for c in rows[header][1:]]
    if not series or not all(_SERIES.match(s) for s in series):
        raise ParseError(f"unexpected series in the header: {series}")
    out = []
    for r in rows[header + 1:]:
        if not r or not r[0].strip():
            continue
        try:
            day = date.fromisoformat(r[0].strip())
        except ValueError:
            raise ParseError(f"bad date {r[0]!r}") from None
        if len(r) - 1 != len(series):
            raise ParseError(f"{day}: {len(r) - 1} values for {len(series)} series")
        for key, cell in zip(series, r[1:], strict=True):
            cell = cell.strip()
            if cell in ("", "ND", "NA", "NC"):  # no data: a holiday, or not published
                continue
            out.append(Obs(key, day, _decimal(cell, f"{day} {key}")))
    return out
