"""SIFMA's historical U.S. holiday recommendations, 1996-2019 (one PDF).

https://www.sifma.org/wp-content/uploads/2017/08/Misc-US-Historical-Holiday-Market-Recommendations-SIFMA.pdf
("SIFMA Holiday Recommendations 1996 - 2019", December 2018) has one page per
year with a five-column table:

    YEAR | REGION | HOLIDAY | RECOMMENDED EARLY CLOSE | RECOMMENDED FULL CLOSE
                               (2PM EST, UNLESS OTHERWISE LISTED)

Plain text loses which column a date sits in, so the parser reads words with
their positions: each page's header gives the column edges, a four-digit
year in the first column starts a row, and lines below it (until the next
year) continue that row's cells. Within a cell:

- Several dates are separated by ";" ("Wednesday, July 3; Friday, July 5").
- Dates usually omit the year: it's the row's year unless the date gives
  one ("Tuesday, December 31, 1996"). Months can be abbreviated ("Jan.",
  "Sept."), and the comma after the weekday is sometimes missing.
- A time in parentheses overrides the 2 p.m. early close: "(noon EST)",
  "(1:00 pm EST)", "(11:00 am EST early close)", "(Early 12:00PM Close)".
- A whole date in parentheses points at the same entry in the next or
  previous year's table (New Year's 2003/2004). It parses like any other
  date, and the copies must agree.
- "NA", "None (holiday falls on Saturday)" and an empty cell mean no
  recommendation; "(observed)" is a note.

Every stated weekday is checked against the date. Two entries fail that
check, and are corrected in CORRECTIONS from the neighbouring tables and the
U.S. Holiday Archive. Anything else the parser doesn't understand fails the
parse; the raw PDF is kept either way.

It also holds two unscheduled recommendations: Hurricane Sandy (an early
close on Oct 29, 2012 and a full close on Oct 30) and the national day of
mourning for George H.W. Bush (a full close on Dec 5, 2018).

This is calendar SIFMA-US's lowest-precedence source: where the archive
(2015-2019) lists a date differently, the archive's row stands and the
disagreement is reported. Coverage: a year counts when its table has a full
set of closes, like the other SIFMA sources.
"""

import io
import re
from datetime import date, time

from app.calendars.parsed import Day, ParsedCalendar, ParseError
from app.calendars.sifma import MIN_FULL_CLOSES, MONTHS, WEEKDAYS

FIRST_YEAR, LAST_YEAR = 1996, 2019
DEFAULT_EARLY_CLOSE = time(14)

# (table year, holiday as named here, the cell entry as printed) -> the date it means.
# Both are New Year's Eve 2016, a Friday: the archive lists it as an early
# close on Friday, December 30, 2016.
CORRECTIONS: dict[tuple[int, str, str], date] = {
    # Year typo in the 2016 table.
    (2016, "New Year's Day", "Friday, December 30, 2015"): date(2016, 12, 30),
    # Day typo in the 2017 table: December 31, 2016 was a Saturday.
    (2017, "New Year's Day", "Friday, December 31, 2016"): date(2016, 12, 30),
}

_WEEKDAY = r"(?P<wd>Monday|Tuesday|Wednesday|Thursday|Friday|Saturday|Sunday)"
_DATE = re.compile(
    _WEEKDAY + r",?\s+(?P<mon>[A-Za-z]+)\.?\s+(?P<dd>\d{1,2})(?:,\s*(?P<yyyy>(?:19|20)\d\d))?",
    re.IGNORECASE,
)
_TIME = re.compile(
    r"(?P<noon>\bnoon\b)|(?P<h>\d{1,2})(?::(?P<m>\d\d))?\s*(?P<ap>[ap])\.?\s*m\b\.?", re.IGNORECASE
)
# A cell with no recommendation in it.
_NONE = re.compile(r"(?:NA|N/A|None)\b.*", re.IGNORECASE)
# Words that may be left in an entry once its date and time are taken out.
_NOISE = re.compile(r"(?:[\s();,.]|\bEST\b|\bearly\b|\bclose\b|\bobserved\b)*", re.IGNORECASE)
# Notes in the holiday column: "(Holiday falls on a Saturday)", "(observed)".
_NAME_NOTE = re.compile(r"\s*\((?:holiday falls on a \w+|observed)\)", re.IGNORECASE)
_NAME_YEAR = re.compile(r"\s+(?:19|20)\d\d$")
_YEAR = re.compile(r"(?:19|20)\d\d")
_MONTH_PREFIX = {m[:3]: n for m, n in MONTHS.items()}
# The PDF's holiday names, as the schedule page and the archive spell them,
# so the same day reads the same from every source (and a name alone is
# never reported as a disagreement).
NAMES = {
    "President's Day": "Presidents Day",
    "Independence Day": "U.S. Independence Day",
    "Thanksgiving": "Thanksgiving Day",
    "Christmas": "Christmas Day",
}
# The page footer (page number) sits below this many points from the bottom.
_FOOTER = 60


def parse(content: bytes) -> ParsedCalendar:
    rows = _rows(content)
    days: dict[date, Day] = {}
    closed: dict[int, int] = {}
    years: set[int] = set()
    for year, region, holiday, early, full in rows:
        if region != "U.S.":
            raise ParseError(f"{year} {holiday!r}: unexpected region {region!r}")
        years.add(year)
        name = _name(holiday)
        found = [Day(d, "early_close", f"{name} (early close)", t) for d, t in _entries(early, year, name, True)]
        found += [Day(d, "closed", name) for d, _ in _entries(full, year, name, False)]
        for day in found:
            old = days.get(day.day)
            if old is not None and old != day:
                raise ParseError(f"{day.day} listed twice, differently: {old} vs {day}")
            days[day.day] = day

    if not years:
        raise ParseError("no holiday tables in the PDF")
    expected = set(range(FIRST_YEAR, LAST_YEAR + 1))
    if years != expected:
        raise ParseError(
            f"expected tables for {FIRST_YEAR}-{LAST_YEAR}; missing {sorted(expected - years)}, "
            f"unexpected {sorted(years - expected)}"
        )
    for d in days.values():
        if d.status == "closed":
            closed[d.day.year] = closed.get(d.day.year, 0) + 1
    short = {y: closed.get(y, 0) for y in sorted(years) if closed.get(y, 0) < MIN_FULL_CLOSES}
    if short:
        raise ParseError(f"years with too few full closes (expected {MIN_FULL_CLOSES}+): {short}")
    return ParsedCalendar(tuple(sorted(years)), tuple(sorted(days.values(), key=lambda d: d.day)))


def _name(holiday: str) -> str:
    name = _NAME_NOTE.sub("", holiday.replace("’", "'")).strip()
    name = _NAME_YEAR.sub("", name)
    if name.upper().startswith("N/A"):  # "N/A (Hurricane Sandy)"
        name = name[3:].strip(" ()")
    if not name:
        raise ParseError(f"empty holiday name in {holiday!r}")
    return NAMES.get(name, name)


def _entries(cell: str, year: int, name: str, early: bool) -> list[tuple[date, time | None]]:
    """The dates in one cell, with each early close's time."""
    cell = cell.replace("’", "'").strip()
    if not cell or _NONE.fullmatch(cell):
        return []
    out = []
    for entry in (e.strip() for e in cell.split(";")):
        if not entry:
            continue
        where = f"{year} {name!r}: {entry!r}"
        m = _DATE.search(entry)
        if m is None:
            raise ParseError(f"{where}: no date")
        rest = entry[: m.start()] + " " + entry[m.end():]
        when = _time(rest, where) if early else None
        rest = _TIME.sub(" ", rest)
        if not _NOISE.fullmatch(rest):
            raise ParseError(f"{where}: can't read {rest.strip()!r}")
        if not early and _TIME.search(entry):
            raise ParseError(f"{where}: a time in the full-close column")
        fixed = CORRECTIONS.get((year, name, _plain(entry)))
        d = fixed or _date(m, year, where)
        out.append((d, (when or DEFAULT_EARLY_CLOSE) if early else None))
    return out


def _plain(entry: str) -> str:
    """An entry without its parentheses, for CORRECTIONS lookups."""
    return " ".join(entry.replace("(", " ").replace(")", " ").split()).rstrip(";")


def _date(m: re.Match, year: int, where: str) -> date:
    mon = _MONTH_PREFIX.get(m["mon"][:3].lower())
    if mon is None:
        raise ParseError(f"{where}: unknown month {m['mon']!r}")
    y = int(m["yyyy"]) if m["yyyy"] else year
    try:
        d = date(y, mon, int(m["dd"]))
    except ValueError:
        raise ParseError(f"{where}: no such date") from None
    if WEEKDAYS[d.weekday()] != m["wd"].lower():
        raise ParseError(f"{where}: {d} is a {d:%A}, not a {m['wd']}")
    if d.weekday() >= 5:
        raise ParseError(f"{where}: {d} is a weekend day")
    if abs(d.year - year) > 1:
        raise ParseError(f"{where}: {d} is far from the {year} table")
    return d


def _time(text: str, where: str) -> time | None:
    found = list(_TIME.finditer(text))
    if not found:
        return None
    if len(found) > 1:
        raise ParseError(f"{where}: more than one close time")
    m = found[0]
    if m["noon"]:
        return time(12)
    h, mi = int(m["h"]), int(m["m"] or 0)
    if not 1 <= h <= 12 or mi > 59:
        raise ParseError(f"{where}: can't read close time {m[0]!r}")
    return time(h % 12 + (12 if m["ap"].lower() == "p" else 0), mi)


def _rows(content: bytes) -> list[tuple[int, str, str, str, str]]:
    """Every table row as (year, region, holiday, early close, full close)."""
    import pdfplumber  # only this source needs it, so it isn't loaded at startup
    from pdfplumber.utils.exceptions import PdfminerException

    try:
        pdf = pdfplumber.open(io.BytesIO(content))
    except PdfminerException as e:  # pdfplumber wraps pdfminer's errors in this
        raise ParseError(f"not a readable PDF: {e}") from None
    rows: list[list] = []
    with pdf:
        for pno, page in enumerate(pdf.pages, 1):
            words = page.extract_words(x_tolerance=1.5)
            edges = _edges(words)
            if edges is None:
                continue  # the cover page
            top = min(w["top"] for w in words if w["text"] == "YEAR") + 30
            body = [w for w in words if w["top"] > top and w["bottom"] < page.height - _FOOTER]
            current = None
            for cells in _lines(body, edges):
                if _YEAR.fullmatch(cells[0]):
                    current = [int(cells[0]), *cells[1:]]
                    rows.append(current)
                elif current is None:
                    if " ".join(cells).strip() not in ("", "LISTED) OTHERWISE", "OTHERWISE LISTED)"):
                        raise ParseError(f"page {pno}: text before the first row: {cells}")
                else:
                    for i, c in enumerate(cells[1:], start=1):
                        if c:
                            current[i] = f"{current[i]} {c}".strip()
    return [tuple(r) for r in rows]


def _edges(words: list[dict]) -> list[float] | None:
    heads = {w["text"]: w["x0"] for w in words if w["text"] in ("YEAR", "REGION", "HOLIDAY")}
    recs = sorted(w["x0"] for w in words if w["text"] == "RECOMMENDED")
    if len(heads) < 3:
        return None
    if len(recs) != 2:
        raise ParseError(f"table header without two 'Recommended' columns: {sorted(heads)}")
    return [heads["YEAR"], heads["REGION"], heads["HOLIDAY"], recs[0], recs[1]]


def _lines(words: list[dict], edges: list[float]) -> list[list[str]]:
    """Words grouped into lines by height, then into the five columns by x."""
    lines: list[list[dict]] = []
    for w in sorted(words, key=lambda w: (round(w["top"]), w["x0"])):
        if lines and abs(lines[-1][0]["top"] - w["top"]) < 3:
            lines[-1].append(w)
        else:
            lines.append([w])
    out = []
    for ws in lines:
        cells = [""] * 5
        for w in sorted(ws, key=lambda w: w["x0"]):
            col = max((i for i, e in enumerate(edges) if w["x0"] >= e - 2), default=0)
            cells[col] = f"{cells[col]} {w['text']}".strip()
        out.append(cells)
    return out
