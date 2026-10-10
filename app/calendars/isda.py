"""ISDA's CDS Standard Model holiday calendars: NYM (New York) and TYO (Tokyo), from cdsmodel.com.

The SPGMI RFR swap curves (app/swaps/sources.py) adjust USD dates on calendar NYM and JPY dates on TYO, "a holiday
calendar published on cdsmodel.com" (SPGMI Interest Rate Curve XML Specification (RFRs), v1.3, section 2.2); the other
currencies use no holidays, weekends only. cdsmodel.com's "ISDA Standard Model Settings for Fee Computations" page
(read 2026-10-10) links the files and says NYM applies from 2022-06-20 and TYO from 2009-09-12; its other calendars
(LDN, TOR, ZRH, TGT, SYD, AKL, SGP, HKG) are kept blank.

These are not banking calendars. Each file is one YYYYMMDD date per line, no header and no names, and lists only the
holidays ISDA has chosen to add: on 2026-10-10 NYM had seven dates (June 20s, Juneteenth landing on the June roll
date) and TYO 88 (around the March and September 20th roll dates). The model treats every other weekday as a
business day, so a file decides every year: the years covered are 1990-2100 (the platform's span), whatever the
listed dates. A weekend date in the file changes nothing (weekends are never business days) and is skipped. calendar
FED and JP stay the banking calendars; ISDA-NYM and ISDA-TYO are what the ISDA model uses.
"""

from datetime import date

from app.calendars.parsed import Day, ParsedCalendar, ParseError

BASE = "https://www.cdsmodel.com/assets/cds-model/csv/"
NYM_URL = BASE + "NYM.csv"
TYO_URL = BASE + "TYO.csv"
YEARS = tuple(range(1990, 2101))


def make_parser(code: str):
    def parse(content: bytes) -> ParsedCalendar:
        return parse_dates(content, code)

    parse.__name__ = f"parse_{code.lower()}"
    return parse


def parse_dates(content: bytes, code: str) -> ParsedCalendar:
    try:
        text = content.decode("utf-8-sig")
    except UnicodeDecodeError:
        raise ParseError(f"ISDA {code}: not text") from None
    days: dict[date, Day] = {}
    for n, raw in enumerate(text.splitlines(), 1):
        line = raw.strip().strip(",").strip()
        if not line:
            continue
        if len(line) != 8 or not line.isdigit():
            raise ParseError(f"ISDA {code}, line {n}: {raw[:40]!r} isn't a YYYYMMDD date")
        try:
            d = date(int(line[:4]), int(line[4:6]), int(line[6:]))
        except ValueError:
            raise ParseError(f"ISDA {code}, line {n}: {line} isn't a date") from None
        if not YEARS[0] <= d.year <= YEARS[-1]:
            raise ParseError(f"ISDA {code}, line {n}: {d} is outside {YEARS[0]}-{YEARS[-1]}")
        if d in days:
            raise ParseError(f"ISDA {code}: {d} listed twice")
        if d.weekday() < 5:
            days[d] = Day(d, "closed", f"ISDA {code} holiday")
    if not days:
        raise ParseError(f"ISDA {code}: no dates")
    return ParsedCalendar(YEARS, tuple(sorted(days.values(), key=lambda x: x.day)))
