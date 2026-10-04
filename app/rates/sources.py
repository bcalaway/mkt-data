"""Treasury constant-maturity (CMT) yield sources (docs/phase-2.md, Part B).

Both are fetched a month at a time, and each month is its own capture period
("2026-10"): a day's fetch of the current month either matches the last
capture of that month (unchanged) or is a new version that adds the day. A
changed value for a day already held is a revision, kept as history.

- UST-PAR: Treasury's Daily Par Yield Curve Rates, XML feed. 1990 on, usually
  up by 6:00 p.m. Eastern the same day. Every tenor, the 1.5-, 2- and 4-month
  points included. The primary source.
- H15-TCM: the Fed's H.15 Treasury constant maturities (nominal, business
  day), CSV from its Data Download Program. The same numbers, published at
  4:15 p.m. Eastern the next business day, back to 1962 for the oldest
  tenors but only 11 of them (no 1.5-, 2- or 4-month). History before 1990,
  and a cross-check. Holidays are rows of "ND".

Step B1 keeps them raw only (no parser yet), so the parsers are written
against real bytes, as phase 1 did with each new document. Both publish on
U.S. Government Securities Business Days: calendar SIFMA-US (calendar-svc).
"""

from dataclasses import dataclass
from datetime import date, datetime
from zoneinfo import ZoneInfo

from sqlalchemy.orm import Session

from app.calendars import service
from app.calendars.service import SourceSpec

EASTERN = ZoneInfo("America/New_York")

UST_PAR_URL = (
    "https://home.treasury.gov/resource-center/data-chart-center/interest-rates/pages/xml"
    "?data=daily_treasury_yield_curve&field_tdr_date_value_month={yyyymm}"
)
# The H.15 package of the 11 nominal Treasury constant maturities, business
# day (RIFLGFCM01_N.B ... RIFLGFCY30_N.B), one month at a time.
H15_TCM_URL = (
    "https://www.federalreserve.gov/datadownload/Output.aspx?rel=H15&series=bf17364827e38702b42a58cf8eaa3f78"
    "&lastobs=&from={first}&to={last}&filetype=csv&label=include&layout=seriescolumn"
)


@dataclass(frozen=True)
class PeriodSource:
    spec: SourceSpec  # name, description, parse (None: kept raw); its url is the template
    calendar: str  # the publication calendar (calendar-svc), for labels and schedules
    first_period: str  # the earliest month the source serves

    def url(self, period: str) -> str:
        y, m = (int(x) for x in period.split("-"))
        first = date(y, m, 1)
        last = date(y + (m == 12), m % 12 + 1, 1)
        last = date.fromordinal(last.toordinal() - 1)
        return self.spec.url.format(
            yyyymm=f"{y:04d}{m:02d}", first=first.strftime("%m/%d/%Y"), last=last.strftime("%m/%d/%Y")
        )


SOURCES: dict[str, PeriodSource] = {
    "UST-PAR": PeriodSource(
        SourceSpec("UST-PAR", UST_PAR_URL, "US Treasury, Daily Par Yield Curve Rates (XML, by month)", None),
        calendar="SIFMA-US", first_period="1990-01",
    ),
    "H15-TCM": PeriodSource(
        SourceSpec("H15-TCM", H15_TCM_URL, "Federal Reserve H.15, Treasury constant maturities, nominal (CSV, by month)", None),
        calendar="SIFMA-US", first_period="1962-01",
    ),
}


class BadPeriod(ValueError):
    pass


def current_period(now: datetime | None = None) -> str:
    now = now or datetime.now(EASTERN)
    return f"{now.year:04d}-{now.month:02d}"


def check_period(name: str, period: str) -> str:
    try:
        y, m = (int(x) for x in period.split("-"))
        if not 1 <= m <= 12 or len(period) != 7:
            raise ValueError
    except ValueError:
        raise BadPeriod(f"period must be YYYY-MM, not {period!r}") from None
    src = SOURCES[name]
    if period < src.first_period or period > current_period():
        raise BadPeriod(f"{name} serves {src.first_period} to {current_period()}, not {period}")
    return f"{y:04d}-{m:02d}"


def run_capture(s: Session, name: str, period: str, fetcher=None) -> dict:
    """Fetch one month of one source and keep it raw if it's new for that month. Commits."""
    src = SOURCES[name]
    period = check_period(name, period)
    cap, is_new, _check = service.capture(s, src.spec, fetcher, url=src.url(period), period=period)
    s.commit()
    out = {"source": name, "period": period, "capture_id": cap.id, "new_capture": is_new,
           "size_bytes": cap.size_bytes}
    if src.spec.parse is None:
        out |= {"parsed": False, "note": service.NOT_PARSED}
    return out
