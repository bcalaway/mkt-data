"""Federal Reserve holidays: the Board's K.8 page.

https://www.federalreserve.gov/aboutthefed/k8.htm lists the holidays the
Federal Reserve System observes for the current year and the next four, as
one table: a header row of years, then one row per holiday with dates like
"January 19", "July 4*" or "July 4**". Per the page's notes:

- `*`: the holiday falls on a Saturday. Reserve Banks and branches are open
  the Friday before (only the Board of Governors closes).
- `**`: it falls on a Sunday. Everything is closed the Monday after.

Calendar FED is the Reserve Banks' operating calendar (Fedwire, the banks
and branches), so its closed weekdays are the weekday holidays plus the
Monday after a Sunday holiday. A Saturday holiday closes no weekday. The
markers are checked against the actual weekday: a mismatch means the page
changed in a way this parser doesn't understand, so it raises instead of
guessing.
"""

import re
from datetime import date, timedelta
from html.parser import HTMLParser

from app.calendars.parsed import Day, ParsedCalendar, ParseError

URL = "https://www.federalreserve.gov/aboutthefed/k8.htm"
# The NY Fed's yearly holiday-schedule circulars, 2003-2009: the published
# record behind FED-RULES for those years (docs/backfill.md). Each is its
# own source, newest first, ranked above the rules: where one disagrees
# with the rules, the circular wins and the difference is reported.
NYFED_CIRCULARS = {
    2009: "https://www.newyorkfed.org/banking/circulars/11980.html",
    2008: "https://www.newyorkfed.org/banking/circulars/11879.html",
    2007: "https://www.newyorkfed.org/banking/circulars/11797.html",
    2006: "https://www.newyorkfed.org/banking/circulars/11720.html",
    2005: "https://www.newyorkfed.org/banking/circulars/11615.html",
    2004: "https://www.newyorkfed.org/banking/circulars/11532.html",
    2003: "https://www.newyorkfed.org/banking/circulars/11465.html",
}

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
CELL = re.compile(r"([A-Za-z]+)\s+(\d{1,2})\s*(\**)")
YEAR = re.compile(r"(?:19|20)\d\d")
# The K.8 page has listed 11 holidays since Juneteenth (2021); fewer means
# a row went missing.
MIN_HOLIDAYS_PER_YEAR = 10


class _Tables(HTMLParser):
    """Every <table> as rows of cell texts (th and td alike)."""

    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.tables: list[list[list[str]]] = []
        self._row: list[str] | None = None
        self._cell: list[str] | None = None

    def handle_starttag(self, tag, attrs):
        if tag == "table":
            self.tables.append([])
        elif tag == "tr" and self.tables:
            self._row = []
        elif tag in ("td", "th") and self._row is not None:
            self._cell = []

    def handle_endtag(self, tag):
        if tag in ("td", "th") and self._cell is not None and self._row is not None:
            self._row.append(" ".join("".join(self._cell).split()))
            self._cell = None
        elif tag == "tr" and self._row is not None and self.tables:
            if self._row:
                self.tables[-1].append(self._row)
            self._row = None

    def handle_data(self, data):
        if self._cell is not None:
            self._cell.append(data)


def _holiday_table(html: str) -> tuple[list[int], list[list[str]]]:
    p = _Tables()
    p.feed(html)
    for table in p.tables:
        if not table:
            continue
        header = table[0]
        years = header[1:]
        if len(years) >= 2 and all(YEAR.fullmatch(y) for y in years):
            return [int(y) for y in years], table[1:]
    raise ParseError("no table with a header row of years")


def parse(content: bytes) -> ParsedCalendar:
    years, rows = _holiday_table(content.decode("utf-8", errors="replace"))
    if years != sorted(set(years)) or years != list(range(years[0], years[-1] + 1)):
        raise ParseError(f"header years aren't consecutive: {years}")
    days: list[Day] = []
    per_year = {y: 0 for y in years}
    for row in rows:
        if len(row) == 1 or not any(row):
            continue  # a note or spacer row spanning the table
        if len(row) != len(years) + 1:
            raise ParseError(f"row has {len(row)} cells, expected {len(years) + 1}: {row}")
        name = row[0]
        if not name:
            raise ParseError(f"row without a holiday name: {row}")
        for year, cell in zip(years, row[1:], strict=True):
            m = CELL.fullmatch(cell)
            if not m or m.group(1).lower() not in MONTHS:
                raise ParseError(f"{name} {year}: can't read date {cell!r}")
            nominal = date(year, MONTHS[m.group(1).lower()], int(m.group(2)))
            marker = m.group(3)
            weekday = nominal.weekday()  # Monday 0 .. Sunday 6
            expected = {5: "*", 6: "**"}.get(weekday, "")
            if marker != expected:
                raise ParseError(
                    f"{name} {nominal}: marker {marker!r} doesn't match its weekday "
                    f"({nominal:%A}); expected {expected!r}"
                )
            per_year[year] += 1
            if weekday < 5:
                days.append(Day(nominal, "closed", name))
            elif weekday == 6:
                days.append(Day(nominal + timedelta(days=1), "closed", f"{name} (observed)"))
            # Saturday: the Reserve Banks stay open on Friday; no weekday closure.
    short = {y: n for y, n in per_year.items() if n < MIN_HOLIDAYS_PER_YEAR}
    if short:
        raise ParseError(f"too few holidays for {short} (expected at least {MIN_HOLIDAYS_PER_YEAR})")
    seen: set[date] = set()
    for d in days:
        if d.day in seen:
            raise ParseError(f"two holidays close {d.day}")
        seen.add(d.day)
    return ParsedCalendar(tuple(years), tuple(sorted(days, key=lambda d: d.day)))
