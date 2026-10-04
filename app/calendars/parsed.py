"""What a calendar parser produces, and the history-keeping diff.

Pure Python (no database), so the rules are unit-tested directly.
"""

from dataclasses import dataclass
from datetime import date, time


class ParseError(ValueError):
    """The source's content doesn't look the way the parser expects.

    Raw content is kept regardless, so a fixed parser can re-run on it.
    """


@dataclass(frozen=True)
class Day:
    """A weekday the calendar is closed (or closes early)."""

    day: date
    status: str  # "closed" | "early_close"
    holiday: str
    close_time: time | None = None


@dataclass(frozen=True)
class ParsedCalendar:
    years: tuple[int, ...]  # every year the source covers, even if a year has no weekday closures
    days: tuple[Day, ...]


@dataclass(frozen=True)
class Diff:
    added: tuple[Day, ...]
    changed: tuple[Day, ...]  # new versions of days whose status, time or name changed
    removed: tuple[date, ...]  # days no longer listed (within the parsed years only)


def diff(current: dict[date, Day], parsed: ParsedCalendar) -> Diff:
    """Compare the current rows with a fresh parse, within the parsed years only.

    Years the source no longer lists (the Fed's page rolls forward each year)
    are left alone: dropping off the page isn't a change to the calendar.
    """
    years = set(parsed.years)
    new = {d.day: d for d in parsed.days}
    added, changed = [], []
    for day, d in sorted(new.items()):
        old = current.get(day)
        if old is None:
            added.append(d)
        elif old != d:
            changed.append(d)
    removed = sorted(day for day in current if day.year in years and day not in new)
    return Diff(tuple(added), tuple(changed), tuple(removed))
