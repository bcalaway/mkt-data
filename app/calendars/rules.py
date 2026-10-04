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

- A holiday is a fixed date ("day") or the n-th weekday of a month ("weekday"
  and "n", where -1 is the last), optionally limited to years "from"/"to".
- Observance moves a weekend holiday: "saturday" is "none" (no weekday
  closes) or "friday"; "sunday" is "none" or "monday". A holiday can
  override either for itself. A moved day is named "<holiday> (observed)".
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
    if (first is None) != (last is None) or (first is not None and not 1900 < first <= last < 2100):
        raise ParseError(f"bad year range {first}-{last}")
    years = tuple(range(first, last + 1)) if first is not None else ()
    default = {"saturday": "none", "sunday": "monday"} | spec.get("observance", {})

    days: dict[date, Day] = {}
    for h in spec.get("holidays", []):
        for y in years:
            if not h.get("from", y) <= y <= h.get("to", y):
                continue
            day = _observed(_nominal(h, y), {**default, **h.get("observance", {})}, h)
            if day is None:
                continue
            if day.day in days and days[day.day] != day:
                raise ParseError(f"two holidays close {day.day}: {days[day.day].holiday}, {day.holiday}")
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


def _nominal(h: dict, year: int) -> date:
    name = h.get("name")
    if not name:
        raise ParseError(f"holiday without a name: {h}")
    month = h.get("month")
    if not isinstance(month, int) or not 1 <= month <= 12:
        raise ParseError(f"{name}: bad month {month!r}")
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


def _observed(d: date, observance: dict, h: dict) -> Day | None:
    name = h["name"]
    if d.weekday() < 5:
        return Day(d, "closed", name)
    rule = observance.get("saturday" if d.weekday() == 5 else "sunday")
    if rule == "none":
        return None
    if d.weekday() == 5 and rule == "friday":
        return Day(d - timedelta(days=1), "closed", f"{name} (observed)")
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
