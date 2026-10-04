"""SIFMA US bond market holiday recommendations.

https://www.sifma.org/resources/general/holiday-schedule/ has a "U.S. Holiday
Recommendations" section (followed by U.K. and Japan), with a tab per year.
Each holiday is a heading, then one or both of:

    Thursday, January 1, 2026                                   (full close)
    Early Close (2:00 p.m. Eastern Time): Wednesday, December 31, 2025

A holiday can be an early close only: Good Friday 2026 is a 12:00 p.m. early
close because it falls on a jobs-report day. SIFMA already lists Saturday and
Sunday holidays on their observed weekday ("U.S. Independence Day (observed)"),
so unlike the Fed's page there's no observance rule to apply here.

The parser reads the section as text lines rather than relying on the page's
markup, which is a CMS layout that changes. It checks every stated weekday
against the date and refuses anything it doesn't understand: the raw capture
is kept either way, so a fixed parser can re-run on it (`reparse`).

Coverage: a year counts as covered only when the page lists a plausible full
set of closes for it (MIN_FULL_CLOSES). The New Year's entry that ends one
year's tab ("New Year's Day 2026/2027") is stored, but doesn't on its own make
2027 covered, so `business-day` keeps answering "not published" for 2027
until SIFMA posts it. Close times are Eastern (the calendar's timezone).
"""

import re
from datetime import date, time

from app.calendars.parsed import Day, ParsedCalendar, ParseError
from app.calendars.text import lines as _lines

URL = "https://www.sifma.org/resources/general/holiday-schedule/"

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

_DATE = (
    r"(Monday|Tuesday|Wednesday|Thursday|Friday|Saturday|Sunday),?\s+"
    r"([A-Za-z]+)\.?\s+(\d{1,2}),?\s+((?:19|20)\d\d)"
)
FULL = re.compile(_DATE, re.IGNORECASE)
EARLY = re.compile(
    r"Early\s+Close\s*\(\s*(\d{1,2})(?::(\d\d))?\s*([ap])\.?\s*m\.?\s*(?:Eastern(?:\s+Time)?|ET)?\s*\)\s*:?\s*"
    + _DATE,
    re.IGNORECASE,
)
EARLY_LABEL = re.compile(r"Early\s+Close\s*\(.*\)\s*:?", re.IGNORECASE)
YEAR_TAB = re.compile(r"(?:19|20)\d\d")
# "New Year's Day 2025/2026" -> "New Year's Day"
NAME_YEARS = re.compile(r"\s+(?:19|20)\d\d\s*/\s*(?:19|20)\d\d$")
US_START = re.compile(r"U\.?\s?S\.?\s+Holiday\s+Recommendations", re.IGNORECASE)
SECTION = re.compile(r"Holiday\s+Recommendations", re.IGNORECASE)
MAX_NAME_LEN = 60
# SIFMA recommends 10-12 full closes a year (11 in 2026, with Good Friday an
# early close). Fewer than this means the year is missing or partial.
MIN_FULL_CLOSES = 9

def _us_section(lines: list[str]) -> list[str]:
    for i, ln in enumerate(lines):
        if US_START.search(ln) and len(ln) <= MAX_NAME_LEN:
            out = []
            for nxt in lines[i + 1:]:
                if SECTION.search(nxt) and len(nxt) <= MAX_NAME_LEN:
                    break  # the U.K. section
                out.append(nxt)
            return out
    raise ParseError("no 'U.S. Holiday Recommendations' section")


def _merge_split_labels(lines: list[str]) -> list[str]:
    """Join an 'Early Close (...):' label with its date if the markup split them."""
    out: list[str] = []
    for ln in lines:
        if out and EARLY_LABEL.fullmatch(out[-1]) and FULL.fullmatch(ln):
            out[-1] = f"{out[-1]} {ln}"
        else:
            out.append(ln)
    return out


def _date(weekday: str, month: str, day: str, year: str, where: str) -> date:
    m = MONTHS.get(month.lower())
    if m is None:
        raise ParseError(f"{where}: unknown month {month!r}")
    try:
        d = date(int(year), m, int(day))
    except ValueError:
        raise ParseError(f"{where}: no such date {month} {day}, {year}") from None
    if weekday.lower() not in WEEKDAYS:
        raise ParseError(f"{where}: unknown weekday {weekday!r}")
    if WEEKDAYS[d.weekday()] != weekday.lower():
        raise ParseError(f"{where}: {d} is a {d:%A}, not a {weekday}")
    if d.weekday() >= 5:
        raise ParseError(f"{where}: {d} is a weekend day")
    return d


def _time(hour: str, minute: str | None, ampm: str, where: str) -> time:
    h, mi = int(hour), int(minute or 0)
    if not 1 <= h <= 12 or mi > 59:
        raise ParseError(f"{where}: can't read close time {hour}:{minute} {ampm}m")
    h = h % 12 + (12 if ampm.lower() == "p" else 0)
    return time(h, mi)


def parse(content: bytes) -> ParsedCalendar:
    section = _merge_split_labels(_us_section(_lines(content.decode("utf-8", errors="replace"))))
    tabs = sorted({int(ln) for ln in section if YEAR_TAB.fullmatch(ln)})
    days: dict[date, Day] = {}
    holiday: str | None = None
    for ln in section:
        if YEAR_TAB.fullmatch(ln):
            continue
        if m := EARLY.fullmatch(ln):
            if holiday is None:
                raise ParseError(f"early close before any holiday heading: {ln!r}")
            when = _date(*m.group(4, 5, 6, 7), where=holiday)
            close = _time(*m.group(1, 2, 3), where=holiday)
            day = Day(when, "early_close", f"{holiday} (early close)", close)
        elif m := FULL.fullmatch(ln):
            if holiday is None:
                raise ParseError(f"date before any holiday heading: {ln!r}")
            day = Day(_date(*m.groups(), where=holiday), "closed", holiday)
        elif EARLY_LABEL.match(ln) or (FULL.search(ln) and len(ln) <= MAX_NAME_LEN):
            raise ParseError(f"can't read {ln!r} (under {holiday!r})")
        else:
            if len(ln) <= MAX_NAME_LEN:
                holiday = NAME_YEARS.sub("", ln).strip()
            continue  # longer lines are notes or disclaimers
        old = days.get(day.day)
        if old is not None and old != day:
            raise ParseError(f"{day.day} listed twice, differently: {old} vs {day}")
        days[day.day] = day

    if not days:
        raise ParseError("no holiday dates in the U.S. section")
    full = {y: 0 for y in {d.day.year for d in days.values()} | set(tabs)}
    for d in days.values():
        if d.status == "closed":
            full[d.day.year] += 1
    years = tuple(sorted(y for y, n in full.items() if n >= MIN_FULL_CLOSES))
    if not years:
        raise ParseError(
            f"no year with at least {MIN_FULL_CLOSES} full closes (full closes per year: {full})"
        )
    return ParsedCalendar(years, tuple(sorted(days.values(), key=lambda d: d.day)))
