"""Japan's national holidays: the Cabinet Office's CSV (calendar JP; docs/phase-4.md, "Calendars").

https://www8.cao.go.jp/chosei/shukujitsu/syukujitsu.csv lists every national
holiday from 1955 to the end of next year, one per line as "YYYY/M/D,name",
under a one-line header, in Shift_JIS (cp932). It includes substitute
holidays (振替休日) and citizens' holidays (国民の休日) as their own dates, so
every listed weekday is a closed day; Saturday and Sunday dates are left out
(they close nothing). Covered years: the first listed to the last. A year with
fewer than 10 holidays means the file changed shape, so it raises instead.

Bank holidays beyond the national ones (December 31 to January 3) come from
the rules file jp_bank.json, not from here.
"""

from datetime import date

from app.calendars.parsed import Day, ParsedCalendar, ParseError

URL = "https://www8.cao.go.jp/chosei/shukujitsu/syukujitsu.csv"
MIN_PER_YEAR = 10


def parse(content: bytes) -> ParsedCalendar:
    try:
        text = content.decode("cp932")
    except UnicodeDecodeError as e:
        raise ParseError(f"Cabinet Office holidays CSV isn't Shift_JIS: {e}") from None
    lines = [ln.strip() for ln in text.splitlines() if ln.strip()]
    if len(lines) < 2:
        raise ParseError("Cabinet Office holidays CSV: no rows")
    listed: dict[date, str] = {}
    for ln in lines[1:]:
        parts = ln.split(",")
        try:
            y, m, d = (int(x) for x in parts[0].split("/"))
            day, name = date(y, m, d), parts[1].strip()
        except (ValueError, IndexError):
            raise ParseError(f"Cabinet Office holidays CSV: can't read {ln!r}") from None
        if not name:
            raise ParseError(f"{day}: no holiday name")
        if day in listed:
            raise ParseError(f"{day} listed twice")
        listed[day] = name
    years = tuple(range(min(listed).year, max(listed).year + 1))
    for y in years:
        n = sum(1 for d in listed if d.year == y)
        if n < MIN_PER_YEAR:
            raise ParseError(f"{y} has {n} national holidays, fewer than {MIN_PER_YEAR}")
    days = tuple(Day(d, "closed", name) for d, name in sorted(listed.items()) if d.weekday() < 5)
    return ParsedCalendar(years, days)
