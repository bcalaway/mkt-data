"""NYSE holidays and early closes: the exchange's hours and calendars page.

https://www.nyse.com/markets/hours-calendars has a "Holidays" table for the
current year and the next two: a header row of years, then one row per
holiday with cells like

    Thursday, January 1
    Friday, July 3 (Independence Day observed)
    Thursday, November 26***
    —*                                  (no holiday observed that year)

Footnotes after the table explain the markers. The ones that matter here
are the early closes, which name their dates in full:

    *** Each market will close early at 1:00 p.m. (1:15 p.m. for eligible
    options) on Friday, November 27, 2026, Friday, November 26, 2027, and
    Friday, November 24, 2028 (the day after Thanksgiving).

Calendar NYSE stores the equities close (1:00 p.m. Eastern), the first time
in the sentence; options and late trading sessions close later and can be
added when a dataset needs them (docs/phase-1.md, open questions).

Like the other parsers it refuses what it doesn't understand rather than
guessing, and the raw page is kept either way (`reparse` after a fix):

- every cell's weekday must match its date, and must be a weekday (the page
  already lists observed days);
- every early close must be a weekday within a few days of a listed
  holiday, which also gives it its name ("Thanksgiving Day (early close)");
- every dated cell carrying a footnote marker must have an early close
  next to it, so a footnote whose wording changed can't silently drop one.

Text is read in block-level lines and table cells, not by CMS class names,
so where the footnotes sit (after the table or inside it) doesn't matter.
"""

import re
from datetime import date, time
from html.parser import HTMLParser

from app.calendars.parsed import Day, ParsedCalendar, ParseError

URL = "https://www.nyse.com/markets/hours-calendars"
# NYSE's "History of New York Stock Exchange Holidays" (1885 to Jan 2011),
# the published record behind NYSE-RULES' 1990-2010 exceptions. Only
# third-party copies survive (docs/backfill.md); this is the most complete.
HISTORY_URL = "https://s3.amazonaws.com/armstrongeconomics-wp/2013/07/NYSE-Closings.pdf"

MONTHS = {
    m: i
    for i, m in enumerate(
        [
            "january", "february", "march", "april", "may", "june",
            "july", "august", "september", "october", "november", "december",
        ],
        start=1,
    )
}
WEEKDAYS = ["monday", "tuesday", "wednesday", "thursday", "friday", "saturday", "sunday"]

_WD = r"(Monday|Tuesday|Wednesday|Thursday|Friday|Saturday|Sunday)"
# A table cell: "Friday, July 3 (Independence Day observed)", "Thursday, November 26***"
CELL = re.compile(
    _WD + r",?\s+([A-Za-z]+)\.?\s+(\d{1,2})\s*(\**)\s*(?:\(([^)]*)\))?\s*(\**)", re.IGNORECASE
)
NO_HOLIDAY = re.compile(r"[—–-]+\s*\**")
YEAR = re.compile(r"(?:19|20)\d\d")
# A full date in a footnote: "Friday, November 27, 2026"
FULL_DATE = re.compile(_WD + r",?\s+([A-Za-z]+)\.?\s+(\d{1,2}),?\s+((?:19|20)\d\d)", re.IGNORECASE)
EARLY = re.compile(r"close\s+early\s+at\s+(\d{1,2})(?::(\d\d))?\s*([ap])\.?\s*m\.?", re.IGNORECASE)
# NYSE observes 10 holidays a year; 9 when New Year's Day falls on a Saturday
# (no Friday observance). Fewer means rows went missing.
MIN_CLOSES_PER_YEAR = 9
# An early close is the day before or after its holiday (Christmas Eve, the
# day after Thanksgiving, July 3); a weekend can sit in between.
MAX_DAYS_FROM_HOLIDAY = 4

_BLOCK = {
    "address", "article", "aside", "blockquote", "br", "button", "dd", "div", "dl", "dt",
    "footer", "h1", "h2", "h3", "h4", "h5", "h6", "header", "hr", "li", "main", "nav",
    "ol", "p", "section", "table", "td", "th", "tr", "ul",
}
_SKIP = {"script", "style", "noscript", "template", "svg"}


def _clean(text: str) -> str:
    return " ".join(text.replace("’", "'").replace("\xa0", " ").split())


class _Page(HTMLParser):
    """The page's visible text as block-level lines, plus every <table> as rows of cells."""

    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.lines: list[str] = []
        self.tables: list[list[list[str]]] = []
        self._buf: list[str] = []
        self._skip = 0
        self._row: list[str] | None = None
        self._cell: list[str] | None = None

    def _flush(self):
        text = _clean("".join(self._buf))
        if text:
            self.lines.append(text)
        self._buf = []

    def handle_starttag(self, tag, attrs):
        if tag in _SKIP:
            self._skip += 1
            return
        if tag in _BLOCK:
            self._flush()
        if tag == "table":
            self.tables.append([])
        elif tag == "tr" and self.tables:
            self._row = []
        elif tag in ("td", "th") and self._row is not None:
            self._cell = []

    def handle_startendtag(self, tag, attrs):
        if tag in _BLOCK:
            self._flush()

    def handle_endtag(self, tag):
        if tag in _SKIP:
            self._skip = max(0, self._skip - 1)
            return
        if tag in _BLOCK:
            self._flush()
        if tag in ("td", "th") and self._cell is not None and self._row is not None:
            self._row.append(_clean("".join(self._cell)))
            self._cell = None
        elif tag == "tr" and self._row is not None and self.tables:
            if self._row:
                self.tables[-1].append(self._row)
            self._row = None

    def handle_data(self, data):
        if self._skip:
            return
        self._buf.append(data)
        if self._cell is not None:
            self._cell.append(data)

    def close(self):
        super().close()
        self._flush()


def _date(weekday: str, month: str, day: str, year: int, where: str) -> date:
    m = MONTHS.get(month.lower())
    if m is None:
        raise ParseError(f"{where}: unknown month {month!r}")
    try:
        d = date(year, m, int(day))
    except ValueError:
        raise ParseError(f"{where}: no such date {month} {day}, {year}") from None
    if WEEKDAYS[d.weekday()] != weekday.lower():
        raise ParseError(f"{where}: {d} is a {d:%A}, not a {weekday}")
    if d.weekday() >= 5:
        raise ParseError(f"{where}: {d} is a weekend day")
    return d


def _time(hour: str, minute: str | None, ampm: str, where: str) -> time:
    h, mi = int(hour), int(minute or 0)
    if not 1 <= h <= 12 or mi > 59:
        raise ParseError(f"{where}: can't read close time {hour}:{minute} {ampm}m")
    return time(h % 12 + (12 if ampm.lower() == "p" else 0), mi)


def _holiday_table(page: _Page) -> tuple[list[int], list[list[str]]]:
    for table in page.tables:
        if not table:
            continue
        years = table[0][1:]
        if len(years) >= 2 and all(YEAR.fullmatch(y) for y in years):
            return [int(y) for y in years], table[1:]
    raise ParseError("no holiday table with a header row of years")


def parse(content: bytes) -> ParsedCalendar:
    page = _Page()
    page.feed(content.decode("utf-8", errors="replace"))
    page.close()

    years, rows = _holiday_table(page)
    if years != list(range(years[0], years[0] + len(years))):
        raise ParseError(f"header years aren't consecutive: {years}")

    closed: dict[date, Day] = {}
    marked: list[tuple[date, str]] = []  # dated cells carrying a footnote marker
    for row in rows:
        if len(row) == 1 or not any(row):
            continue  # a note or spacer row spanning the table
        if len(row) != len(years) + 1:
            raise ParseError(f"row has {len(row)} cells, expected {len(years) + 1}: {row}")
        name = row[0]
        if not name:
            raise ParseError(f"row without a holiday name: {row}")
        for year, cell in zip(years, row[1:], strict=True):
            if NO_HOLIDAY.fullmatch(cell):
                continue  # e.g. New Year's Day on a Saturday: nothing observed
            m = CELL.fullmatch(cell)
            if not m:
                raise ParseError(f"{name} {year}: can't read {cell!r}")
            where = f"{name} {year}"
            d = _date(m.group(1), m.group(2), m.group(3), year, where)
            note = m.group(5) or ""
            holiday = f"{name} (observed)" if "observed" in note.lower() else name
            if d in closed:
                raise ParseError(f"two holidays on {d}: {closed[d].holiday} and {holiday}")
            closed[d] = Day(d, "closed", holiday)
            if m.group(4) or m.group(6):
                marked.append((d, name))

    per_year = {y: 0 for y in years}
    for d in closed:
        per_year[d.year] += 1
    short = {y: n for y, n in per_year.items() if n < MIN_CLOSES_PER_YEAR}
    if short:
        raise ParseError(f"too few holidays for {short} (expected at least {MIN_CLOSES_PER_YEAR})")

    early: dict[date, Day] = {}
    for line in page.lines:
        if not (t := EARLY.search(line)):
            continue
        dates = list(FULL_DATE.finditer(line))
        if not dates:
            raise ParseError(f"early-close note without a full date: {line!r}")
        for m in dates:
            year = int(m.group(4))
            d = _date(m.group(1), m.group(2), m.group(3), year, where=f"early close {m.group(0)!r}")
            if year not in per_year:
                raise ParseError(f"early close {d} is outside the table's years {years}")
            if d in closed:
                raise ParseError(f"{d} is both a holiday and an early close")
            near = sorted(
                (abs((h - d).days), h) for h in closed if abs((h - d).days) <= MAX_DAYS_FROM_HOLIDAY
            )
            if not near:
                raise ParseError(f"early close {d} isn't next to any listed holiday")
            name = closed[near[0][1]].holiday.removesuffix(" (observed)")
            day = Day(d, "early_close", f"{name} (early close)", _time(*t.groups(), where=str(d)))
            if d in early and early[d] != day:
                raise ParseError(f"{d} listed twice, differently: {early[d]} vs {day}")
            early[d] = day

    for d, name in marked:
        if not any(abs((e - d).days) <= MAX_DAYS_FROM_HOLIDAY for e in early):
            raise ParseError(f"{name} {d} has a footnote marker but no early close was found next to it")

    days = sorted([*closed.values(), *early.values()], key=lambda x: x.day)
    return ParsedCalendar(tuple(years), tuple(days))
