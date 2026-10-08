"""Japan's national holidays: the Cabinet Office's CSV (calendar JP; docs/phase-4.md, "Calendars").

https://www8.cao.go.jp/chosei/shukujitsu/syukujitsu.csv lists every national
holiday from 1955 to the end of next year, one per line as "YYYY/M/D,name",
under a one-line header, in Shift_JIS (cp932). It includes substitute
holidays (振替休日) and citizens' holidays (国民の休日) as their own dates, so
every listed weekday is a closed day; Saturday and Sunday dates are left out
(they close nothing). Covered years: the first listed to the last. A year with
fewer than 9 holidays (the 1950s had nine) means the file changed shape, so it raises instead.

Names are given in English, as the projection (jp_projected.json) names them.
The file's 休日 ("holiday") is either a substitute holiday, named after the
Sunday holiday it stands in for ("Children's Day (observed)"), or a citizens'
holiday, a day between two holidays ("Citizens' Holiday"); the dates around
it tell which. A name not in ENGLISH raises, so a new holiday (a law change or
an imperial ceremony) gets an English name before it's loaded.

Bank holidays beyond the national ones (December 31 to January 3) come from
the rules file jp_bank.json, not from here.
"""

from datetime import date, timedelta

from app.calendars.parsed import Day, ParsedCalendar, ParseError

URL = "https://www8.cao.go.jp/chosei/shukujitsu/syukujitsu.csv"
MIN_PER_YEAR = 9  # 1955-1958 and 1960 had nine (the 1948 Act's list); 10 or more since

HOLIDAY = "休日"  # a substitute or a citizens' holiday: named from the dates around it (english_names)
ENGLISH = {
    "元日": "New Year's Day",
    "成人の日": "Coming of Age Day",
    "建国記念の日": "National Foundation Day",
    "天皇誕生日": "Emperor's Birthday",
    "春分の日": "Vernal Equinox Day",
    "昭和の日": "Showa Day",
    "憲法記念日": "Constitution Memorial Day",
    "みどりの日": "Greenery Day",
    "こどもの日": "Children's Day",
    "海の日": "Marine Day",
    "山の日": "Mountain Day",
    "敬老の日": "Respect for the Aged Day",
    "秋分の日": "Autumnal Equinox Day",
    "体育の日": "Health and Sports Day",  # Sports Day's name until 2019
    "体育の日（スポーツの日）": "Sports Day",  # 2019's listing, as the rename was enacted
    "スポーツの日": "Sports Day",
    "文化の日": "Culture Day",
    "勤労感謝の日": "Labour Thanksgiving Day",
    "結婚の儀": "Imperial Wedding",  # 1959 (Crown Prince Akihito), 1993 (Crown Prince Naruhito)
    "大喪の礼": "State Funeral of Emperor Showa",  # 1989-02-24
    "即位礼正殿の儀": "Enthronement Ceremony",  # 1990-11-12
    # "A holiday, treated as a national holiday": 2019's two one-off holidays (special act), named by date.
    "休日（祝日扱い）": "Holiday (treated as a national holiday)",
}
ONE_OFF = {date(2019, 5, 1): "Accession of the Emperor", date(2019, 10, 22): "Enthronement Ceremony"}


def english_names(listed: dict[date, str]) -> dict[date, str]:
    """Each listed day's English name; raises on a name it doesn't know."""
    out = {}
    for day, name in listed.items():
        if day in ONE_OFF:
            out[day] = ONE_OFF[day]
        elif name == HOLIDAY:
            out[day] = _holiday_name(day, listed)
        elif name in ENGLISH:
            out[day] = ENGLISH[name]
        else:
            raise ParseError(f"{day}: no English name for {name!r} (add it to jpcao.ENGLISH)")
    return out


def _holiday_name(day: date, listed: dict[date, str]) -> str:
    """A substitute holiday follows a run of holidays that includes a Sunday (the nearest, with no other 休日 between);
    otherwise a 休日 between two listed days is a citizens' holiday."""
    d = day - timedelta(days=1)
    while d in listed and listed[d] != HOLIDAY:
        if d.weekday() == 6:
            return f"{ENGLISH[listed[d]]} (observed)"
        d -= timedelta(days=1)
    if day - timedelta(days=1) in listed and day + timedelta(days=1) in listed:
        return "Citizens' Holiday"
    raise ParseError(f"{day}: a 休日 that's neither a substitute nor between two holidays")


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
    names = english_names(listed)
    days = tuple(Day(d, "closed", names[d]) for d in sorted(listed) if d.weekday() < 5)
    return ParsedCalendar(years, days)
