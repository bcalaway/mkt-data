"""Parser for the ISDA standard model's RFR swap curves (S&P Global Market Intelligence; docs/phase-4.md, "Swap curves").

One capture is one currency's file for one publication date: a zip holding one XML document (the spec's section 4)
and S&P's disclaimer text, or the XML itself. The layout, from the SPGMI Interest Rate Curve XML Specification (RFRs), v1.3, 2026-06-15:

    <?xml version='1.0' encoding='UTF-8'?>
    <IHSM ...>                        root (named for IHS Markit; any name is accepted)
      <interestRateCurve>
        <effectiveasof>2021-02-24</effectiveasof>   the trade date the curve is for (T)
        <currency>GBP</currency>
        <baddayconvention>M</baddayconvention>
        <ois>
          <fixeddaycountconvention>ACT/365</fixeddaycountconvention>
          <floatingdaycountconvention>ACT/365</floatingdaycountconvention>
          <fixedpaymentfrequency>1Y</fixedpaymentfrequency>
          <floatingpaymentfrequency>1Y</floatingpaymentfrequency>
          <snaptime>2021-02-23T16:00:00</snaptime>  local to the currency's reference city
          <spotdate>2021-02-24</spotdate>
          <calendars><calendar>none</calendar></calendars>
          <curvepoint><tenor>1M</tenor><maturitydate>2021-03-23</maturitydate><parrate>0.000508</parrate></curvepoint>
          ...
        </ois>
      </interestRateCurve>
    </IHSM>

The file is published on T-1 weekday and used for trade date T (section 5.5), so its date here (`as_of`, which places
it in its capture's period) is the weekday before `effectiveasof`: the publication date in the file's name, and the
date of the close it was snapped at. If the zip member's name carries a date, it must agree.

Two kinds of near-raw rows, both as printed:

- Observations: one per curve point, key the tenor as printed (`1M`, `10Y`), field `parrate`, unit `decimal` (the
  file's rates are already decimals: 0.000508 = 0.0508%).
- One record per file, type `curve`, key the publication date: every header and `ois` field as printed, the
  calendars, and the curve points (tenor, maturity date, par rate). That's what secmaster-svc reads to check the swap
  instruments' conventions against, and what keeps the file's own maturity and spot dates (ISDA's model takes them
  directly).
"""

import io
import re
import xml.etree.ElementTree as ET
import zipfile
from datetime import date, timedelta
from decimal import Decimal, InvalidOperation

from app.calendars.parsed import ParseError
from app.rates.parsers import Obs
from app.securities.parsers import Rec

FIELD = "parrate"
UNIT = "decimal"
HEADER = ("effectiveasof", "currency", "baddayconvention")
OIS = ("fixeddaycountconvention", "floatingdaycountconvention", "fixedpaymentfrequency", "floatingpaymentfrequency",
       "snaptime", "spotdate")
TENOR = re.compile(r"^\d{1,2}[DWMY]$")
MEMBER_DATE = re.compile(r"(\d{8})")


def xml_of(body: bytes) -> tuple[bytes, str]:
    """The XML document in a capture, and the zip member's name ("" when the capture is the XML itself)."""
    if body[:2] == b"PK":
        try:
            with zipfile.ZipFile(io.BytesIO(body)) as z:
                # The XML, and beside it S&P's "ISDA Standard Rate Curves Disclaimer.txt" (seen on the first
                # captures, 2026-10-10), kept in the raw capture and not parsed.
                names = [n for n in z.namelist() if n.lower().endswith(".xml")]
                if len(names) != 1:
                    raise ParseError(f"expected one .xml file in the zip, found {len(names)}: {z.namelist()[:5]}")
                return z.read(names[0]), names[0]
        except zipfile.BadZipFile as e:
            raise ParseError(f"not a readable zip: {e}") from None
    if body.lstrip()[:1] == b"<":
        return body, ""
    raise ParseError(f"neither a zip nor XML (starts {body[:40]!r})")


def curve_view(body: bytes) -> bytes:
    """The capture without its zip wrapper (dates and compression differ from one download to the next), for
    deciding whether a re-fetch is unchanged."""
    try:
        return xml_of(body)[0]
    except ParseError as e:
        raise ValueError(str(e)) from None


def _local(tag: str) -> str:
    return tag.rsplit("}", 1)[-1]


def _child(el: ET.Element, name: str) -> ET.Element | None:
    return next((c for c in el if _local(c.tag) == name), None)


def _text(el: ET.Element, name: str, where: str) -> str:
    c = _child(el, name)
    if c is None or c.text is None or not c.text.strip():
        raise ParseError(f"{where}: no {name}")
    return c.text.strip()


def _date(text: str, where: str) -> date:
    try:
        return date.fromisoformat(text[:10])
    except ValueError:
        raise ParseError(f"{where}: bad date {text!r}") from None


def previous_weekday(d: date) -> date:
    d -= timedelta(days=1)
    while d.weekday() >= 5:
        d -= timedelta(days=1)
    return d


def make_parser(currency: str):
    """The parser for one currency's source: a file for another currency is a ParseError."""

    def parse(body: bytes) -> tuple[list[Obs], list[Rec]]:
        return parse_curve(body, currency)

    parse.__name__ = f"parse_curve_{currency.lower()}"
    return parse


def parse_curve(body: bytes, currency: str) -> tuple[list[Obs], list[Rec]]:
    doc, member = xml_of(body)
    try:
        root = ET.fromstring(doc)
    except ET.ParseError as e:
        raise ParseError(f"not well-formed XML: {e}") from None
    curve = root if _local(root.tag) == "interestRateCurve" else _child(root, "interestRateCurve")
    if curve is None:
        raise ParseError(f"no interestRateCurve under <{_local(root.tag)}>")
    fields: dict = {name: _text(curve, name, "interestRateCurve") for name in HEADER}
    if fields["currency"] != currency:
        raise ParseError(f"a {fields['currency']} curve, expected {currency}")
    effective = _date(fields["effectiveasof"], "effectiveasof")
    as_of = previous_weekday(effective)
    m = MEMBER_DATE.search(member)
    if m:
        try:
            named = date(int(m[1][:4]), int(m[1][4:6]), int(m[1][6:]))
        except ValueError:
            raise ParseError(f"zip member {member!r}: bad date") from None
        if named != as_of:
            raise ParseError(f"zip member {member!r} is dated {named}, but effectiveasof {effective} makes it {as_of}")
    ois = _child(curve, "ois")
    if ois is None:
        raise ParseError("no ois element")
    for name in OIS:
        fields[name] = _text(ois, name, "ois")
    _date(fields["spotdate"], "spotdate")
    cals = _child(ois, "calendars")
    fields["calendars"] = [c.text.strip() for c in (cals if cals is not None else []) if c.text and c.text.strip()]
    if not fields["calendars"]:
        raise ParseError("no calendars (a curve with no holidays says 'none')")
    points, obs = [], []
    for cp in (c for c in ois if _local(c.tag) == "curvepoint"):
        tenor = _text(cp, "tenor", "curvepoint")
        where = f"curvepoint {tenor}"
        if not TENOR.match(tenor):
            raise ParseError(f"{where}: unexpected tenor")
        maturity = _text(cp, "maturitydate", where)
        if _date(maturity, where) <= effective:
            raise ParseError(f"{where}: maturity {maturity} isn't after the trade date {effective}")
        printed = _text(cp, "parrate", where)
        try:
            rate = Decimal(printed)
        except InvalidOperation:
            raise ParseError(f"{where}: parrate {printed!r} isn't a number") from None
        if not rate.is_finite():
            raise ParseError(f"{where}: parrate {printed!r} isn't a number")
        points.append({"tenor": tenor, "maturitydate": maturity, "parrate": printed})
        obs.append(Obs(tenor, as_of, rate, FIELD, UNIT))
    if not points:
        raise ParseError("no curve points")
    if len({p["tenor"] for p in points}) != len(points):
        raise ParseError("a tenor appears twice")
    fields["curvepoints"] = points
    return obs, [Rec("curve", as_of.isoformat(), as_of, fields)]
