"""The NY Fed's yearly holiday-schedule circulars, 2003-2009 (FED-NYFED-<year>).

Each circular is one year's published list of the Federal Reserve Bank of New
York's holidays: the record behind FED-RULES for those years (docs/backfill.md).
Ranked above the rules, so where the two disagree the circular wins and the
rules' version is reported as held_by_higher_source.

What the page's visible text looks like (captures #15-#22, 2026-10-04):

    All offices of the Federal Reserve Bank of New York are closed on all
    Saturdays and Sundays and for the following holiday observances in the year 2005:
    New Year's Day
    Sat, Jan 1
    ...
    Christmas Day
    Sun, Dec 25
    Christmas Day (December 25) falls on a Sunday. As a result, the Bank will
    be closed on the following day (Monday, December 26).

- The list is name/date line pairs, ten holidays. 2003 adds "Holiday" and
  "Date Observed in 2003" headers and writes dates in full ("Wednesday,
  January 1"); later years abbreviate ("Thu, Jan 1", once "Tue, July 4").
- A Saturday holiday closes nothing: the Banks stay open the Friday before
  (2004's Christmas, 2009's Independence Day).
- A Sunday holiday comes with a note naming the Monday the Bank closes.
  Without that note, a Sunday is an error rather than a guess.
- 2004 lists Independence Day directly on its observed Monday ("Mon, Jul 5").

Names follow FED-RULES (5 U.S.C. 6103): "Washington's Birthday", and a
fixed-date holiday moved to another day is "<name> (observed)". So the
cross-check reports only real differences (a date or a status), not wording.
"""

import re
from datetime import date

from app.calendars import text
from app.calendars.parsed import Day, ParsedCalendar, ParseError

INTRO = re.compile(r"are closed on all Saturdays and Sundays and for the following holiday observances in the year (\d{4}):")
HEADERS = re.compile(r"^(Holiday|Date Observed in \d{4})$")
DATE = re.compile(
    r"^(Mon|Tue|Wed|Thu|Fri|Sat|Sun)[a-z]*,\s+([A-Z][a-z]+)\.?\s+(\d{1,2})$"
)
SUNDAY_NOTE = re.compile(
    r"^(?P<name>.+?) \((?P<mon>[A-Z][a-z]+) (?P<dd>\d{1,2})\) falls on a Sunday\. As a result, the Bank will be closed "
    r"on the following day \((?P<wd>Monday), (?P<mon2>[A-Z][a-z]+) (?P<dd2>\d{1,2})\)\.$"
)
MONTHS = {m: i for i, m in enumerate(
    ["jan", "feb", "mar", "apr", "may", "jun", "jul", "aug", "sep", "oct", "nov", "dec"], start=1)}
WEEKDAYS = ["mon", "tue", "wed", "thu", "fri", "sat", "sun"]
NAMES = {  # the circulars' wording -> FED-RULES' names
    "Washington's Birthday (Presidents' Day)": "Washington's Birthday",
    "Presidents' Day": "Washington's Birthday",
}
FIXED = {  # fixed-date holidays: moved to another day, they're "(observed)"
    "New Year's Day": (1, 1), "Independence Day": (7, 4), "Veterans Day": (11, 11), "Christmas Day": (12, 25),
}
EXPECTED_HOLIDAYS = 10


def _month(name: str, where: str) -> int:
    m = MONTHS.get(name[:3].lower())
    if m is None:
        raise ParseError(f"{where}: unknown month {name!r}")
    return m


def _date(year: int, weekday: str, month: str, day: str, where: str) -> date:
    try:
        d = date(year, _month(month, where), int(day))
    except ValueError:
        raise ParseError(f"{where}: no such date {month} {day}, {year}") from None
    if WEEKDAYS[d.weekday()] != weekday[:3].lower():
        raise ParseError(f"{where}: {d} is a {d:%A}, not a {weekday}")
    return d


def _closed(name: str, d: date) -> Day:
    fixed = FIXED.get(name)
    label = f"{name} (observed)" if fixed and (d.month, d.day) != fixed else name
    return Day(d, "closed", label)


def parse(content: bytes) -> ParsedCalendar:
    lines = text.lines(content.decode("utf-8", errors="replace"))
    start = next((i for i, ln in enumerate(lines) if INTRO.search(ln)), None)
    if start is None:
        raise ParseError("no 'closed on all Saturdays and Sundays ... in the year' line")
    year = int(INTRO.search(lines[start])[1])

    listed: list[tuple[str, date]] = []
    notes: dict[str, date] = {}  # holiday name -> the Monday a Sunday holiday moves to
    i = start + 1
    while i < len(lines):
        ln = lines[i]
        if HEADERS.match(ln):
            i += 1
        elif (m := SUNDAY_NOTE.match(ln)):
            name = NAMES.get(m["name"], m["name"])
            notes[name] = _date(year, m["wd"], m["mon2"], m["dd2"], where=f"{year} note")
            i += 1
        elif i + 1 < len(lines) and (m := DATE.match(lines[i + 1])) and not DATE.match(ln):
            name = NAMES.get(ln, ln)
            listed.append((name, _date(year, *m.groups(), where=f"{year} {name}")))
            i += 2
        else:
            break  # past the list: "Bank's ... Holiday Schedule", signatures, the site's footer

    if len(listed) != EXPECTED_HOLIDAYS:
        raise ParseError(f"{year}: expected {EXPECTED_HOLIDAYS} holidays, read {len(listed)}: {listed}")
    days: list[Day] = []
    for name, d in listed:
        if d.weekday() == 5:
            continue  # Saturday: the Banks stay open the Friday before
        if d.weekday() == 6:
            moved = notes.pop(name, None)
            if moved is None:
                raise ParseError(f"{year}: {name} falls on Sunday {d} but there's no note saying when the Bank closes")
            days.append(_closed(name, moved))
        else:
            days.append(_closed(name, d))
    if notes:
        raise ParseError(f"{year}: a Sunday note for a holiday that isn't on a Sunday: {notes}")
    return ParsedCalendar((year,), tuple(sorted(days, key=lambda x: x.day)))
