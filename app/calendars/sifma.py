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

The U.S. Holiday Archive (ARCHIVE_URL, `parse_archive`) has the same entries
for past years (2015-2025 as of 2026-10-04), one section per year, newest
first. It's calendar SIFMA-US's second source, below the current page in
precedence. Its real wording (capture #4, 2026-10-04) has a few older forms:

- "Early Close Only (…): <date> – <note>" (Good Friday 2021 and 2023).
- "Early Close (12:00 Noon Eastern Time) Friday, April 3, 2015", with no colon,
  right under that holiday's own date line "Friday, April 3, 2015". Under one
  holiday, an early close on the holiday's own date means the day closes
  early rather than fully (SIFMA's noon close for the 2015 jobs report), so
  the early close replaces the date line. The same date listed two ways under
  different holidays is still an error.
- "Early Market Close: (2:00 p.m. Eastern Time): Friday, December 30, 2016".
- Headings with no date (Presidents Day 2015 and 2016, Veterans Day 2023) or
  with "None" (Veterans Day 2017, a Saturday): no recommendation is stored.
- The 1996-2017 PDF link ("US Holiday Archives 1996-2017") ends the years.
"""

import re
from datetime import date, time

from app.calendars.parsed import Day, ParsedCalendar, ParseError
from app.calendars.text import lines as _lines

URL = "https://www.sifma.org/resources/general/holiday-schedule/"
ARCHIVE_URL = "https://www.sifma.org/resources/guides-playbooks/us-holiday-archive"
# Historical recommendations, 1996-2019, one PDF table per year (linked from
# the archive page as "US Holiday Archives 1996-2017"). Parsed by
# app/calendars/sifma_history.py, which reads cell positions.
HISTORY_URL = (
    "https://www.sifma.org/wp-content/uploads/2017/08/Misc-US-Historical-Holiday-Market-Recommendations-SIFMA.pdf"
)

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
# "Early Close (2:00 p.m. Eastern Time): Wednesday, December 31, 2025", and the
# archive's variants: "Early Close Only (…)", "(12:00 Noon Eastern Time)" with
# no colon after it, and a trailing note ("… 2021 – Confirmed based on …").
EARLY = re.compile(
    r"Early\s+(?:Market\s+)?Close(?:\s+Only)?\s*:?\s*\(\s*"
    r"(?:(?P<h>\d{1,2})(?::(?P<m>\d\d))?\s*(?:(?P<ap>[ap])\.?\s*m\.?|(?P<noon>noon))|(?P<bare_noon>noon))"
    r"\s*(?:Eastern(?:\s+Time)?|E\.?T\.?)?\s*\)\s*:?\s*"
    r"(?P<wd>Monday|Tuesday|Wednesday|Thursday|Friday|Saturday|Sunday),?\s+"
    r"(?P<mon>[A-Za-z]+)\.?\s+(?P<dd>\d{1,2}),?\s+(?P<yyyy>(?:19|20)\d\d)"
    r"(?:\s*[–—-]\s*\S.*)?",
    re.IGNORECASE,
)
EARLY_LABEL = re.compile(r"Early\s+(?:Market\s+)?Close(?:\s+Only)?\s*:?\s*\(.*\)\s*:?", re.IGNORECASE)
# Any line that starts like an early close must parse as one, however long:
# a long unread one would otherwise pass as a note and leave a quiet gap.
EARLY_START = re.compile(r"Early\s+(?:Market\s+)?Close\b", re.IGNORECASE)
# The holiday has no recommendation that year ("Veterans Day" / "None").
NO_DATE = re.compile(r"None\.?", re.IGNORECASE)
YEAR_TAB = re.compile(r"(?:19|20)\d\d")
# "New Year's Day 2025/2026" -> "New Year's Day"
NAME_YEARS = re.compile(r"\s+(?:19|20)\d\d\s*/\s*(?:19|20)\d\d$")
US_START = re.compile(r"U\.?\s?S\.?\s+Holiday\s+Recommendations", re.IGNORECASE)
SECTION = re.compile(r"Holiday\s+Recommendations", re.IGNORECASE)
MAX_NAME_LEN = 60
# SIFMA recommends 10-12 full closes a year (11 in 2026, with Good Friday an
# early close). Fewer than this means the year is missing or partial.
MIN_FULL_CLOSES = 9
# The archive held 2015-2025 when this was written (2026-10-04); far fewer
# year headings means the page changed shape.
MIN_ARCHIVE_YEARS = 5
OTHER_ARCHIVE = re.compile(r"^(?:U\.?\s?K\.?|Japan)\b.*(?:Holiday|Archive)", re.IGNORECASE)
# "US Holiday Archives 1996-2017", the PDF link after the last year.
PDF_LINK = re.compile(r"Holiday\s+Archives?\s+(?:19|20)\d\d\s*[-–]\s*(?:19|20)\d\d", re.IGNORECASE)

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


def _time(m: re.Match, where: str) -> time:
    if m["bare_noon"]:
        return time(12)
    h, mi = int(m["h"]), int(m["m"] or 0)
    if m["noon"]:
        if (h, mi) != (12, 0):
            raise ParseError(f"{where}: can't read close time {m['h']}:{m['m']} noon")
        return time(12)
    if not 1 <= h <= 12 or mi > 59:
        raise ParseError(f"{where}: can't read close time {m['h']}:{m['m']} {m['ap']}m")
    return time(h % 12 + (12 if m["ap"].lower() == "p" else 0), mi)


def parse(content: bytes) -> ParsedCalendar:
    """SIFMA's current schedule page: the U.S. section's published year tabs."""
    return _parse(_us_section(_lines(content.decode("utf-8", errors="replace"))), archive=False)


def parse_archive(content: bytes) -> ParsedCalendar:
    """SIFMA's U.S. Holiday Archive: a section per past year, newest first.

    Same entries as the schedule page. Every year heading must come with a
    full set of closes: a year with fewer means a line the parser didn't
    understand, so it fails rather than leave a quiet gap.
    """
    return _parse(_archive_section(_lines(content.decode("utf-8", errors="replace"))), archive=True)


def _archive_section(lines: list[str]) -> list[str]:
    for i, ln in enumerate(lines):
        if YEAR_TAB.fullmatch(ln):
            out = []
            for nxt in lines[i:]:
                if (SECTION.search(nxt) or OTHER_ARCHIVE.search(nxt) or PDF_LINK.search(nxt)) and len(
                    nxt
                ) <= MAX_NAME_LEN:
                    break  # another market's section, or the PDF link after the last year
                out.append(nxt)
            return out
    raise ParseError("no year headings in the archive")


def _parse(lines: list[str], archive: bool) -> ParsedCalendar:
    section = _merge_split_labels(lines)
    tabs = sorted({int(ln) for ln in section if YEAR_TAB.fullmatch(ln)})
    days: dict[date, Day] = {}
    holiday: str | None = None
    under_holiday: set[date] = set()  # dates written under the current heading
    for ln in section:
        if YEAR_TAB.fullmatch(ln):
            continue
        if NO_DATE.fullmatch(ln):
            if holiday is None:
                raise ParseError(f"{ln!r} before any holiday heading")
            continue
        if m := EARLY.fullmatch(ln):
            if holiday is None:
                raise ParseError(f"early close before any holiday heading: {ln!r}")
            when = _date(m["wd"], m["mon"], m["dd"], m["yyyy"], where=holiday)
            close = _time(m, where=holiday)
            day = Day(when, "early_close", f"{holiday} (early close)", close)
        elif m := FULL.fullmatch(ln):
            if holiday is None:
                raise ParseError(f"date before any holiday heading: {ln!r}")
            day = Day(_date(*m.groups(), where=holiday), "closed", holiday)
        elif EARLY_START.match(ln) or EARLY_LABEL.match(ln) or (FULL.search(ln) and len(ln) <= MAX_NAME_LEN):
            raise ParseError(f"can't read {ln!r} (under {holiday!r})")
        else:
            if len(ln) <= MAX_NAME_LEN:
                holiday = NAME_YEARS.sub("", ln).strip()
                under_holiday = set()
            continue  # longer lines are notes or disclaimers
        old = days.get(day.day)
        if old is not None and old != day:
            if day.day in under_holiday and {old.status, day.status} == {"closed", "early_close"}:
                # The holiday's date line plus an early close on that same
                # date (Good Friday 2015): it closes early, not fully.
                day = old if old.status == "early_close" else day
            else:
                raise ParseError(f"{day.day} listed twice, differently: {old} vs {day}")
        days[day.day] = day
        under_holiday.add(day.day)

    if not days:
        raise ParseError("no holiday dates in the U.S. section")
    full = {y: 0 for y in {d.day.year for d in days.values()} | set(tabs)}
    for d in days.values():
        if d.status == "closed":
            full[d.day.year] += 1
    if archive:
        short = {y: full[y] for y in tabs if full[y] < MIN_FULL_CLOSES}
        if short:
            raise ParseError(f"archive years with too few full closes (expected {MIN_FULL_CLOSES}+): {short}")
        if len(tabs) < MIN_ARCHIVE_YEARS:
            raise ParseError(f"only {len(tabs)} year headings in the archive: {tabs}")
    years = tuple(sorted(y for y, n in full.items() if n >= MIN_FULL_CLOSES))
    if not years:
        raise ParseError(
            f"no year with at least {MIN_FULL_CLOSES} full closes (full closes per year: {full})"
        )
    return ParsedCalendar(years, tuple(sorted(days.values(), key=lambda d: d.day)))
