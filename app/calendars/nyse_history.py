"""NYSE's "History of New York Stock Exchange Holidays" PDF (NYSE-HISTORY).

The published record behind NYSE-RULES' 1990-2010 exceptions
(docs/backfill.md). Only third-party copies survive; capture #17
(2026-10-04) is the "Revised through January 2011" copy.

The document is not a per-year holiday list. It has the regular holidays as
policy prose, then "NEW YORK STOCK EXCHANGE SPECIAL CLOSINGS, 1885-date": a
chronological list of one-off full closes and early closes, mixed with
opening delays, short halts and moments of silence. So this source covers no
years (like SIFMA-US-EXCEPTIONS): it contributes the special full closes and
early closes it lists for 1990-2010, outranks NYSE-RULES on those dates, and
leaves every other day to the rules. Where the rules disagree on one of its
dates, apply() reports the rules' version as held_by_higher_source.

Entries start "Mon. D, YYYY (Wkd)" or, for ranges, "Sept. 11-14, 2001 (Tue-Fri)".
What counts:
- an early close: "Closed at 1:00 pm", "Floor closed at 2:30 pm", "Trading
  floor closed at 2:00 pm", a circuit-breaker "halt at 3:30 pm that ended
  trading for the day" (Oct 27, 1997), and a halt after which "Trading did
  not resume" (June 1, 2005, 3:56 pm);
- a full close: an entry starting "Closed" with no time (funerals, days of
  mourning, Sept 11-14, 2001).
What doesn't: opening delays, halts that resumed, moments of silence, and a
close later than the regular 4:00 pm (July 2, 2009, 4:15 pm, to clear
orders after a systems problem). Any other entry that mentions closing is
an error, not a guess.

Labels follow NYSE-RULES ("Christmas Day (early close)", "September 11
attacks", ...), so the cross-check reports only real differences (a date, a
status or a time), not wording.
"""

import io
import re
from datetime import date, time, timedelta

from app.calendars.parsed import Day, ParsedCalendar, ParseError

FIRST_YEAR, LAST_YEAR = 1990, 2010
REGULAR_CLOSE = time(16, 0)
SPECIAL = re.compile(r"NEW YORK STOCK EXCHANGE SPECIAL CLOSINGS")
MONTH = r"(Jan|Feb|Mar|Apr|May|June|July|Aug|Sept|Oct|Nov|Dec)\.?"
ENTRY = re.compile(
    rf"^{MONTH} (?P<d1>\d{{1,2}})(?:-(?P<d2>\d{{1,2}}))?, (?P<y>\d{{4}}) "
    r"\((?P<w1>[A-Z][a-z]{2})\.?(?:-(?P<w2>[A-Z][a-z]{2})\.?)?\)\s*(?P<rest>.*)$"
)
FOOTNOTE = re.compile(r"^\d+ [A-Z]")  # "2 Not a closing - ..."
PAGE_NUMBER = re.compile(r"^\d+$")
MONTHS = {"jan": 1, "feb": 2, "mar": 3, "apr": 4, "may": 5, "jun": 6, "jul": 7,
          "aug": 8, "sep": 9, "oct": 10, "nov": 11, "dec": 12}
TIME = r"(\d{1,2}):(\d{2}) ?(am|pm)"
EARLY = [
    re.compile(rf"\bClosed at {TIME}", re.IGNORECASE),  # "Closed at 1:00 pm. ..." or "Christmas Eve. Closed at 2:00 pm."
    re.compile(rf"(?:Trading )?floor closed at {TIME}", re.IGNORECASE),
    re.compile(rf"halt at {TIME} that ended trading for the day", re.IGNORECASE),
    re.compile(rf"Trading was halted at {TIME}.*Trading did not resume", re.IGNORECASE),
]
NOT_A_CLOSE = re.compile(
    r"observed (one|two|one-minute)|moments? of silen|minute of silen|Opening delayed|delayed opening|"
    r"Trading reopened|halted trading|halts trading|Trading was halted",
    re.IGNORECASE,
)
# Reason text -> NYSE-RULES' label. Early closes get " (early close)".
LABELS = [
    (re.compile(r"Thanksgiving", re.IGNORECASE), "Thanksgiving Day"),
    (re.compile(r"Christmas", re.IGNORECASE), "Christmas Day"),
    (re.compile(r"Independence Day", re.IGNORECASE), "Independence Day"),
    (re.compile(r"New Year", re.IGNORECASE), "New Year's Day"),
    (re.compile(r"snowstorm", re.IGNORECASE), "Snowstorm"),
    (re.compile(r"Circuit breakers", re.IGNORECASE), "Circuit breaker halt"),
    (re.compile(r"systems communications problem", re.IGNORECASE), "Systems halt"),
    (re.compile(r"Nixon", re.IGNORECASE), "Funeral of President Nixon"),
    (re.compile(r"terrorist attack on the World", re.IGNORECASE), "September 11 attacks"),
    (re.compile(r"Reagan", re.IGNORECASE), "National Day of Mourning (President Reagan)"),
    (re.compile(r"Ford", re.IGNORECASE), "National Day of Mourning (President Ford)"),
]
WEEKDAYS = ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"]


def _text(content: bytes) -> list[str]:
    import pdfplumber  # only the PDF sources need it, so it isn't loaded at startup (as in sifma_history)
    from pdfplumber.utils.exceptions import PdfminerException

    try:
        with pdfplumber.open(io.BytesIO(content)) as pdf:
            pages = [p.extract_text() or "" for p in pdf.pages]
    except PdfminerException as e:  # pdfplumber wraps pdfminer's errors in this
        raise ParseError(f"can't read the PDF: {e}") from None
    return [ln.strip() for page in pages for ln in page.splitlines() if ln.strip()]


def _entries(lines: list[str]) -> list[tuple[re.Match, str]]:
    """(entry header match, full entry text), continuation lines joined."""
    start = next((i for i, ln in enumerate(lines) if SPECIAL.search(ln)), None)
    if start is None:
        raise ParseError("no 'NEW YORK STOCK EXCHANGE SPECIAL CLOSINGS' list")
    out: list[list] = []
    in_footnote = False
    for ln in lines[start + 1:]:
        if m := ENTRY.match(ln):
            out.append([m, m["rest"]])
            in_footnote = False
        elif FOOTNOTE.match(ln):
            in_footnote = True  # footnotes and their continuation lines aren't entries
        elif PAGE_NUMBER.match(ln) or in_footnote or not out:
            continue
        else:
            out[-1][1] += " " + ln
    return [(m, re.sub(r"\s+", " ", t).strip()) for m, t in out]


def _dates(m: re.Match) -> list[date]:
    year, month = int(m["y"]), MONTHS[m[1][:3].lower()]
    try:
        first = date(year, month, int(m["d1"]))
        last = date(year, month, int(m["d2"])) if m["d2"] else first
    except ValueError:
        raise ParseError(f"no such date: {m.group(0)[:40]!r}") from None
    days = [first + timedelta(n) for n in range((last - first).days + 1)]
    if WEEKDAYS[first.weekday()] != m["w1"] or WEEKDAYS[last.weekday()] != (m["w2"] or m["w1"]):
        raise ParseError(f"weekday doesn't match the date: {m.group(0)[:40]!r}")
    return days


def _label(reason: str, where: str) -> str:
    for pattern, label in LABELS:
        if pattern.search(reason):
            return label
    raise ParseError(f"{where}: a close with no known reason: {reason[:80]!r}")


def parse(content: bytes) -> ParsedCalendar:
    return parse_lines(_text(content))


def parse_lines(lines: list[str]) -> ParsedCalendar:
    """The parse on the PDF's text lines (split out for tests)."""
    days: dict[date, Day] = {}
    for m, entry in _entries(lines):
        if not FIRST_YEAR <= int(m["y"]) <= LAST_YEAR:
            continue
        where = m.group(0)[:30]
        early = next((p.search(entry) for p in EARLY if p.search(entry)), None)
        if early:
            h, mi, ap = int(early[1]), int(early[2]), early[3].lower()
            close = time(h % 12 + (12 if ap == "pm" else 0), mi)
            if close >= REGULAR_CLOSE:
                continue  # a late close (July 2, 2009, 4:15 pm), not an early one
            label = f"{_label(entry, where)} (early close)"
            new = [Day(d, "early_close", label, close) for d in _dates(m)]
        elif entry.lower().startswith("closed"):
            label = _label(entry, where)
            new = [Day(d, "closed", label) for d in _dates(m)]
        elif NOT_A_CLOSE.search(entry) or not re.search(r"clos", entry, re.IGNORECASE):
            continue
        else:
            raise ParseError(f"{where}: can't tell whether this is a close: {entry[:80]!r}")
        for d in new:
            if d.day.weekday() >= 5:
                raise ParseError(f"{where}: {d.day} is a weekend day")
            if d.day in days and days[d.day] != d:
                raise ParseError(f"{d.day} listed twice, differently")
            days[d.day] = d
    if not days:
        raise ParseError(f"no special closings read for {FIRST_YEAR}-{LAST_YEAR}")
    return ParsedCalendar((), tuple(sorted(days.values(), key=lambda x: x.day)))
