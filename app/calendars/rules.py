"""Rule sets and cited exceptions: versioned JSON files in this repo.

Where no published document reaches back far enough, a calendar's older
years come from rules (docs/backfill.md): the holidays' dates by statute or
exchange rule, how a weekend holiday is observed, and dated exceptions,
each with a citation. Each file under app/calendars/rules/ is a source
whose URL is `repo:<file name>`. Its capture is the file's exact bytes, so
a change to the rules becomes a new capture and the processed rows still
point at the version that produced them.

A file looks like this (every field but "calendar" is optional):

    {
      "calendar": "FED",
      "first_year": 1986, "last_year": 2025,
      "observance": {"saturday": "none", "sunday": "monday"},
      "holidays": [
        {"name": "Memorial Day", "month": 5, "weekday": "monday", "n": -1, "from": 1971},
        {"name": "Christmas Day", "month": 12, "day": 25}
      ],
      "exceptions": [
        {"date": "2025-01-09", "status": "early_close", "close_time": "14:00",
         "holiday": "...", "citation": "https://..."}
      ],
      "citations": ["https://..."]
    }

- A holiday is a fixed date ("month" and "day"), the n-th weekday of a month
  ("month", "weekday" and "n", where -1 is the last), a weekday relative to a
  date ("month", "day", "weekday" and "match": "on_or_before",
  "on_or_after" or "nearest": Canada's Victoria Day is the Monday on or
  before May 24), a day relative to Easter Sunday ("easter": -2 is Good
  Friday), or a table of dates by year ("dates": {"2022": "06-24"}, for a
  holiday set year by year, such as New Zealand's Matariki), optionally
  limited to years "from"/"to". "offset" shifts it by that many days (the day after
  Thanksgiving is the 4th Thursday of November, offset 1).
- A holiday is a full close unless it says "status": "early_close" with a
  "close_time". Such a rule can be limited to some days of the week
  ("weekdays": ["monday", ...]); on any other day it doesn't apply, and it's
  never moved.
- Observance moves a weekend holiday: "saturday" is "none" (no weekday
  closes), "friday" or "monday"; "sunday" is "none" or "monday". A holiday
  can override either for itself. A moved day is named "<holiday> (observed)".
  With "collision": "next", a moved day that lands on another holiday goes
  to the next free weekday instead (the UK: Christmas on a Saturday is the
  Monday, Boxing Day on the Sunday then the Tuesday; and Boxing Day on a
  Monday stays, so Christmas on the Sunday before moves to the Tuesday).
  Holidays on weekdays are placed first, then the moved ones. Without it, two
  holidays on one day are an error.
- An exception sets one date: "closed", "early_close" (with "close_time")
  or "open" (removes a day the rules would close). Every exception needs a
  citation.
- first_year/last_year are the years the file covers. Without them it
  covers none: a list of exceptions to other sources adds its dates
  without claiming any year is complete.
"""

import json
from datetime import date, time, timedelta
from pathlib import Path

from app.calendars.parsed import Day, ParsedCalendar, ParseError

RULES_DIR = Path(__file__).resolve().parent / "rules"
REPO_PREFIX = "repo:"
WEEKDAYS = ["monday", "tuesday", "wednesday", "thursday", "friday", "saturday", "sunday"]
STATUSES = ("closed", "early_close", "open")


def read(url: str) -> bytes:
    """A `repo:` source's bytes. Raises FileNotFoundError for an unknown file."""
    name = url.removeprefix(REPO_PREFIX)
    path = (RULES_DIR / name).resolve()
    if path.parent != RULES_DIR or not path.is_file():
        raise FileNotFoundError(f"no rules file {name!r} in {RULES_DIR.name}/")
    return path.read_bytes()


def parse(content: bytes) -> ParsedCalendar:
    try:
        spec = json.loads(content)
    except (UnicodeDecodeError, json.JSONDecodeError) as e:
        raise ParseError(f"rules file isn't valid JSON: {e}") from None
    if not isinstance(spec, dict) or not spec.get("calendar"):
        raise ParseError("rules file needs a 'calendar'")
    first, last = spec.get("first_year"), spec.get("last_year")
    if (first is None) != (last is None) or (first is not None and not 1900 < first <= last <= 2100):
        raise ParseError(f"bad year range {first}-{last}")
    years = tuple(range(first, last + 1)) if first is not None else ()
    default = {"saturday": "none", "sunday": "monday"} | spec.get("observance", {})

    days: dict[date, Day] = {}
    for y in years:
        nominals = []
        for h in spec.get("holidays", []):
            if not h.get("from", y) <= y <= h.get("to", y):
                continue
            d = _nominal(h, y)
            if d is not None:
                nominals.append((h, d + timedelta(days=h.get("offset", 0))))
        # Weekday holidays first, so a moved weekend holiday never displaces a holiday on its own day.
        nominals.sort(key=lambda x: x[1].weekday() >= 5)
        for h, nominal in nominals:
            observance = {**default, **h.get("observance", {})}
            if h.get("status", "closed") == "early_close":
                day = _early(nominal, h)
            else:
                day = _observed(nominal, observance, h)
            if day is None:
                continue
            if day.day in days and days[day.day] != day:
                if observance.get("collision") != "next" or nominal.weekday() < 5:
                    raise ParseError(f"two holidays close {day.day}: {days[day.day].holiday}, {day.holiday}")
                d = day.day
                while d in days or d.weekday() >= 5:
                    d += timedelta(days=1)
                day = Day(d, day.status, day.holiday, day.close_time)
            days[day.day] = day

    seen = set()
    for x in spec.get("exceptions", []):
        d, status = _exception_date(x), x.get("status")
        if d in seen:
            raise ParseError(f"exception {d} listed twice")
        seen.add(d)
        if status not in STATUSES:
            raise ParseError(f"exception {d}: status must be one of {STATUSES}")
        if not str(x.get("citation", "")).startswith("https://"):
            raise ParseError(f"exception {d}: needs a citation URL")
        if status == "open":
            if d not in days:
                raise ParseError(f"exception {d} opens a day the rules don't close")
            del days[d]
            continue
        if not x.get("holiday"):
            raise ParseError(f"exception {d}: needs a holiday name")
        close = _time(x, d) if status == "early_close" else None
        days[d] = Day(d, status, x["holiday"], close)
    return ParsedCalendar(years, tuple(sorted(days.values(), key=lambda x: x.day)))


MATCHES = ("on_or_before", "on_or_after", "nearest")


def _nominal(h: dict, year: int) -> date | None:
    """The holiday's date in a year before observance; None if a table of dates has no date that year."""
    name = h.get("name")
    if not name:
        raise ParseError(f"holiday without a name: {h}")
    if "easter" in h:
        return easter(year) + timedelta(days=h["easter"])
    if "dates" in h:
        table = h["dates"]
        if not isinstance(table, dict):
            raise ParseError(f"{name}: 'dates' must map years to MM-DD")
        md = table.get(str(year))
        if md is None:
            return None
        try:
            return date.fromisoformat(f"{year}-{md}")
        except ValueError:
            raise ParseError(f"{name}: bad date {md!r} for {year}") from None
    month = h.get("month")
    if not isinstance(month, int) or not 1 <= month <= 12:
        raise ParseError(f"{name}: bad month {month!r}")
    if "day" in h and "match" in h:
        if h["match"] not in MATCHES or h.get("weekday") not in WEEKDAYS:
            raise ParseError(f"{name}: 'match' needs a 'weekday' and one of {MATCHES}")
        anchor, target = date(year, month, h["day"]), WEEKDAYS.index(h["weekday"])
        before = anchor - timedelta(days=(anchor.weekday() - target) % 7)
        after = anchor + timedelta(days=(target - anchor.weekday()) % 7)
        if h["match"] == "on_or_before":
            return before
        if h["match"] == "on_or_after":
            return after
        return before if (anchor - before) <= (after - anchor) else after
    if "day" in h:
        return date(year, month, h["day"])
    wd, n = h.get("weekday"), h.get("n")
    if wd not in WEEKDAYS or n not in (1, 2, 3, 4, -1):
        raise ParseError(f"{name}: needs a 'day', or a 'weekday' and 'n' (1-4 or -1)")
    target = WEEKDAYS.index(wd)
    if n == -1:
        d = date(year + month // 12, month % 12 + 1, 1) - timedelta(days=1)
        return d - timedelta(days=(d.weekday() - target) % 7)
    d = date(year, month, 1)
    return d + timedelta(days=(target - d.weekday()) % 7 + 7 * (n - 1))


def easter(year: int) -> date:
    """Easter Sunday (Gregorian calendar; the anonymous algorithm)."""
    a, b, c = year % 19, year // 100, year % 100
    d, e = b // 4, b % 4
    g = (8 * b + 13) // 25
    h = (19 * a + b - d - g + 15) % 30
    i, k = c // 4, c % 4
    l = (32 + 2 * e + 2 * i - h - k) % 7
    m = (a + 11 * h + 19 * l) // 433
    month = (h + l - 7 * m + 90) // 25
    return date(year, month, (h + l - 7 * m + 33 * month + 19) % 32)


def _early(d: date, h: dict) -> Day | None:
    allowed = h.get("weekdays", WEEKDAYS[:5])
    if any(w not in WEEKDAYS[:5] for w in allowed):
        raise ParseError(f"{h['name']}: 'weekdays' can only list Monday to Friday")
    if WEEKDAYS[d.weekday()] not in allowed:
        return None
    try:
        close = time.fromisoformat(h["close_time"])
    except (KeyError, TypeError, ValueError):
        raise ParseError(f"{h['name']}: an early-close rule needs 'close_time' as HH:MM") from None
    return Day(d, "early_close", h["name"], close)


def _observed(d: date, observance: dict, h: dict) -> Day | None:
    name = h["name"]
    if d.weekday() < 5:
        return Day(d, "closed", name)
    rule = observance.get("saturday" if d.weekday() == 5 else "sunday")
    if rule == "none":
        return None
    if d.weekday() == 5 and rule == "friday":
        return Day(d - timedelta(days=1), "closed", f"{name} (observed)")
    if d.weekday() == 5 and rule == "monday":
        return Day(d + timedelta(days=2), "closed", f"{name} (observed)")
    if d.weekday() == 6 and rule == "monday":
        return Day(d + timedelta(days=1), "closed", f"{name} (observed)")
    raise ParseError(f"{name}: unknown observance {rule!r} for {d:%A}")


def _exception_date(x: dict) -> date:
    try:
        d = date.fromisoformat(x["date"])
    except (KeyError, TypeError, ValueError):
        raise ParseError(f"exception without a valid 'date': {x}") from None
    if d.weekday() >= 5 and x.get("status") != "open":
        raise ParseError(f"exception {d} is a weekend day")
    return d


def _time(x: dict, d: date) -> time:
    try:
        return time.fromisoformat(x["close_time"])
    except (KeyError, TypeError, ValueError):
        raise ParseError(f"exception {d}: an early close needs 'close_time' as HH:MM") from None
