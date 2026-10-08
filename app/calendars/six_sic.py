"""SIX's SIC banking holidays: the published PDF (calendar CH; docs/phase-4.md, "Calendars").

SIX publishes one page, "The schedule of clearing days for SIC, euroSIC, ...
during bank holidays in <year> has been determined by the competent banking
committees in consultation with SIX", with a table of rows like

    Friday 1 January 2027 New Year's Day No No

the day, date and holiday, then whether it's a clearing day for SIC (and
LSV+/BDD in francs) and for euroSIC. The table runs from the previous
Christmas Eve to the next January 2, but only the year named in the heading
is covered: the rows outside it belong to the neighbouring years' lists. A
weekday row with SIC "No" is a closed day; "Yes" (Christmas Eve, New Year's
Eve) is a normal clearing day; weekend rows close nothing. Anything else in a
row, a weekday that doesn't match its date, or fewer than MIN_ROWS rows in
the covered year means the PDF changed shape, so it raises.
"""

import io
import re
from datetime import date

from app.calendars.parsed import Day, ParsedCalendar, ParseError

HEADING = re.compile(r"bank\s+holidays\s+in\s+(\d{4})")
ROW = re.compile(
    r"(?P<weekday>Monday|Tuesday|Wednesday|Thursday|Friday|Saturday|Sunday) "
    r"(?P<date>\d{1,2} [A-Z][a-z]+ \d{4}) (?P<holiday>.+?) (?P<sic>Yes|No) (?P<eurosic>Yes|No|\*)"
)
MIN_ROWS = 10  # the ten holidays and two eves; a year always lists them all, weekends included
MONTHS = ("January", "February", "March", "April", "May", "June", "July", "August", "September", "October",
          "November", "December")
WEEKDAYS = ("Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday")
QUOTES = str.maketrans({"‘": "'", "’": "'"})  # the PDF's typographic apostrophes


def _text(content: bytes) -> str:
    import pdfplumber  # only this source needs it, so it isn't loaded at startup
    from pdfplumber.utils.exceptions import PdfminerException

    try:
        pdf = pdfplumber.open(io.BytesIO(content))
    except PdfminerException as e:  # pdfplumber wraps pdfminer's errors in this
        raise ParseError(f"not a readable PDF: {e}") from None
    with pdf:
        return "\n".join(page.extract_text() or "" for page in pdf.pages)


def parse(content: bytes) -> ParsedCalendar:
    text = _text(content)
    heading = HEADING.search(" ".join(text.split()))
    if heading is None:
        raise ParseError("SIX SIC holidays: no 'bank holidays in <year>' heading")
    year = int(heading[1])
    rows = []
    for line in text.splitlines():
        line = " ".join(line.split())
        if not re.match(r"(Mon|Tues|Wednes|Thurs|Fri|Satur|Sun)day \d", line):
            continue  # the heading, the column titles, the footnotes
        m = ROW.fullmatch(line)
        if m is None:
            raise ParseError(f"SIX SIC holidays: can't read {line!r}")
        try:
            d, month, y = m["date"].split()
            day = date(int(y), MONTHS.index(month) + 1, int(d))
        except ValueError:
            raise ParseError(f"SIX SIC holidays: can't read the date in {line!r}") from None
        if WEEKDAYS[day.weekday()] != m["weekday"]:
            raise ParseError(f"SIX SIC holidays: {m['date']} isn't a {m['weekday']}")
        rows.append((day, m["holiday"].translate(QUOTES), m["sic"]))
    covered = [r for r in rows if r[0].year == year]
    if len(covered) < MIN_ROWS:
        raise ParseError(f"SIX SIC holidays: {len(covered)} rows for {year}, fewer than {MIN_ROWS}")
    if len({d for d, _, _ in covered}) != len(covered):
        raise ParseError(f"SIX SIC holidays: a date listed twice in {year}")
    days = tuple(Day(d, "closed", name) for d, name, sic in sorted(covered) if sic == "No" and d.weekday() < 5)
    return ParsedCalendar((year,), days)


