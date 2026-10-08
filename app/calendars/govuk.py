"""UK bank holidays: gov.uk's JSON (calendar GB; docs/phase-4.md, "Calendars").

https://www.gov.uk/bank-holidays.json lists the bank holidays of three
divisions (england-and-wales, scotland, northern-ireland), from 2019 to two
or so years ahead, each as {"title", "date" (YYYY-MM-DD), "notes",
"bunting"}. Calendar GB is London's, so only england-and-wales is read: every
event is a closed weekday (gov.uk lists the substitute day, with notes
"Substitute day", not the weekend date). The years covered are every year
from the first event's to the last's; a year with fewer than the eight
standing holidays means the file changed shape, so it raises instead.
"""

import json
from datetime import date

from app.calendars.parsed import Day, ParsedCalendar, ParseError

URL = "https://www.gov.uk/bank-holidays.json"
DIVISION = "england-and-wales"
STANDING = 8  # New Year, Good Friday, Easter Monday, early May, spring, summer, Christmas, Boxing Day


def parse(content: bytes) -> ParsedCalendar:
    try:
        doc = json.loads(content)
        events = doc[DIVISION]["events"]
    except (UnicodeDecodeError, json.JSONDecodeError, KeyError, TypeError) as e:
        raise ParseError(f"gov.uk bank holidays: no {DIVISION} events ({e})") from None
    days: dict[date, Day] = {}
    for ev in events:
        try:
            d = date.fromisoformat(ev["date"])
            title = ev["title"].strip()
        except (KeyError, TypeError, ValueError, AttributeError):
            raise ParseError(f"gov.uk bank holidays: can't read event {ev!r}") from None
        if d.weekday() >= 5:
            raise ParseError(f"{d} ({title}) is a weekend day: gov.uk lists substitute days, not weekend dates")
        if (ev.get("notes") or "").strip().lower() == "substitute day":
            title = f"{title} (substitute day)"
        if d in days:
            raise ParseError(f"{d} listed twice: {days[d].holiday}, {title}")
        days[d] = Day(d, "closed", title)
    if not days:
        raise ParseError("gov.uk bank holidays: no events")
    years = tuple(range(min(days).year, max(days).year + 1))
    for y in years:
        n = sum(1 for d in days if d.year == y)
        if n < STANDING:
            raise ParseError(f"{y} has {n} bank holidays, fewer than the {STANDING} standing ones")
    return ParsedCalendar(years, tuple(sorted(days.values(), key=lambda x: x.day)))
