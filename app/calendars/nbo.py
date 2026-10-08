"""Norges Bank's settlement days page (calendar NO; docs/phase-4.md, "Calendars").

https://www.norges-bank.no/en/topics/Norges-Banks-settlement-system/Settlement-days/
says "NBO is closed on Saturdays and Sundays and on the following public
holidays:", then a year on its own line and that year's days, one a line:

    17 May: Constitution Day (Sunday)

Weekend days are listed with their weekday in brackets; they close nothing
extra and are dropped. Two holidays on one date (Whit Monday on Constitution
Day, 2027) are one day, "Constitution Day and Whit Monday", as the rules name it. Each year heading is a covered year (the page lists
the current year, and the next once Norges Bank adds it). A row that doesn't
read as a date, a date in the wrong year, a year with fewer than MIN_ROWS
rows, or no list at all means the page changed shape, so it raises.
"""

import re
from datetime import date

from app.calendars import text
from app.calendars.parsed import Day, ParsedCalendar, ParseError

INTRO = "NBO is closed on Saturdays and Sundays and on the following public holidays:"
MONTHS = ("January", "February", "March", "April", "May", "June", "July", "August", "September", "October",
          "November", "December")
ROW = re.compile(r"(?P<day>\d{1,2}) (?P<month>[A-Z][a-z]+): (?P<name>.+?)(?: \((?P<weekday>[A-Z][a-z]+day)\))?")
WEEKDAYS = ("Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday")
MIN_ROWS = 10  # eleven holidays a year, weekend ones included


def parse(content: bytes) -> ParsedCalendar:
    lines = text.lines(content.decode("utf-8", errors="replace"))
    try:
        start = lines.index(INTRO) + 1
    except ValueError:
        raise ParseError(f"Norges Bank settlement days: no line {INTRO!r}") from None
    rows: dict[int, list[tuple[date, str]]] = {}
    year = None
    for line in lines[start:]:
        if re.fullmatch(r"\d{4}", line):
            year = int(line)
            rows[year] = []
            continue
        m = ROW.fullmatch(line)
        if m is None:
            break  # the end of the list ("Edited ...")
        if year is None or m["month"] not in MONTHS:
            raise ParseError(f"Norges Bank settlement days: can't read {line!r}")
        try:
            day = date(year, MONTHS.index(m["month"]) + 1, int(m["day"]))
        except ValueError:
            raise ParseError(f"Norges Bank settlement days: {line!r} isn't a date in {year}") from None
        if m["weekday"] and m["weekday"] != WEEKDAYS[day.weekday()]:
            raise ParseError(f"Norges Bank settlement days: {day} isn't a {m['weekday']}")
        rows[year].append((day, m["name"]))
    if not rows:
        raise ParseError("Norges Bank settlement days: no year listed")
    for y, rs in rows.items():
        if len(rs) < MIN_ROWS:
            raise ParseError(f"Norges Bank settlement days: {len(rs)} days for {y}, fewer than {MIN_ROWS}")
    names: dict[date, list[str]] = {}
    for rs in rows.values():
        for d, name in rs:
            names.setdefault(d, []).append(name)
    days = tuple(Day(d, "closed", " and ".join(names[d])) for d in sorted(names) if d.weekday() < 5)
    return ParsedCalendar(tuple(sorted(rows)), days)
