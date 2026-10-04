"""Phase 2, step A4: does calendar-svc's golden calendar equal calendar_day?

calendar-svc now builds FED, SIFMA-US and NYSE from mkt-data's near-raw rows.
Before anything switches over to it (A5), its calendars must match the ones
mkt-data has built since phase 1, for every date 1900-2100 and every covered
year:

- days: the same closed and early-close weekdays, with the same status,
  Eastern close time and holiday name;
- years: the same covered years, each credited to a source of the same kind
  (published, rules or projected), which is also what the business-day
  answer's `projected` flag comes from.

`compare` is pure; the calendar-svc side comes from its gRPC `Calendars`
service (proto/calendars.proto, a copy of calendar-svc's) through `CalendarSvc`.
"""

from datetime import date

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.calendars import service
from app.models import Calendar, CalendarDay, CalendarYear, Capture, Source

START, END = date(1900, 1, 1), date(2100, 12, 31)
MAX_LISTED = 50  # differences listed per kind; the counts are always complete


def ours(s: Session, name: str) -> tuple[dict, dict]:
    """mkt-data's calendar: {date: (status, close_time, holiday)} and {year: (source, kind)}."""
    cal = s.scalar(select(Calendar).where(Calendar.name == name))
    if cal is None:
        return {}, {}
    days = {
        r.day.isoformat(): (r.status, r.close_time.strftime("%H:%M") if r.close_time else "", r.holiday)
        for r in s.scalars(select(CalendarDay).where(CalendarDay.calendar_id == cal.id, CalendarDay.valid_to.is_(None)))
    }
    years = {}
    for year, src in s.execute(
        select(CalendarYear.year, Source.name)
        .join(Capture, Capture.id == CalendarYear.capture_id).join(Source, Source.id == Capture.source_id)
        .where(CalendarYear.calendar_id == cal.id)
    ):
        spec = service.SOURCES.get(src)
        years[year] = (src, service.source_kind(spec) if spec else "published")
    return days, years


def theirs(closes: list[dict], coverage: list[dict]) -> tuple[dict, dict]:
    """calendar-svc's answer in the same shape."""
    days = {c["date"]: (c["status"], c["close_time"], c["holiday"]) for c in closes}
    years = {int(y["year"]): (y["source"], y["kind"]) for y in coverage}
    return days, years


def compare(name: str, mine: tuple[dict, dict], other: tuple[dict, dict]) -> dict:
    my_days, my_years = mine
    svc_days, svc_years = other
    only_ours = sorted(set(my_days) - set(svc_days))
    only_svc = sorted(set(svc_days) - set(my_days))
    differ = sorted(d for d in set(my_days) & set(svc_days) if my_days[d] != svc_days[d])
    years_only_ours = sorted(set(my_years) - set(svc_years))
    years_only_svc = sorted(set(svc_years) - set(my_years))
    kind_differs = sorted(y for y in set(my_years) & set(svc_years) if my_years[y][1] != svc_years[y][1])
    source_differs = sorted(y for y in set(my_years) & set(svc_years) if my_years[y][0] != svc_years[y][0])
    equal = not (only_ours or only_svc or differ or years_only_ours or years_only_svc or kind_differs)
    return {
        "calendar": name,
        "equal": equal,
        "days": {"ours": len(my_days), "calendar_svc": len(svc_days)},
        "years": {"ours": len(my_years), "calendar_svc": len(svc_years)},
        "days_only_in_mkt_data": only_ours[:MAX_LISTED], "days_only_in_mkt_data_count": len(only_ours),
        "days_only_in_calendar_svc": only_svc[:MAX_LISTED], "days_only_in_calendar_svc_count": len(only_svc),
        "days_that_differ": [{"date": d, "mkt_data": my_days[d], "calendar_svc": svc_days[d]} for d in differ[:MAX_LISTED]],
        "days_that_differ_count": len(differ),
        "years_only_in_mkt_data": years_only_ours, "years_only_in_calendar_svc": years_only_svc,
        "years_whose_kind_differs": [{"year": y, "mkt_data": my_years[y], "calendar_svc": svc_years[y]} for y in kind_differs],
        # Same kind but a different source credited: worth seeing, not a failure.
        "years_credited_to_another_source": len(source_differs),
    }


class CalendarSvc:
    """calendar-svc's Calendars service over gRPC."""

    def __init__(self, target: str):
        self.target = target

    def read(self, name: str) -> tuple[list[dict], list[dict]]:
        import grpc  # here, so the rest of the app (and its tests) runs without compiled grpcio

        from app.grpc_gen import calendars_pb2 as pb
        from app.grpc_gen import calendars_pb2_grpc as pb_grpc

        with grpc.insecure_channel(self.target) as channel:
            stub = pb_grpc.CalendarsStub(channel)
            closes = stub.Closes(pb.ClosesRequest(calendar=name, start=START.isoformat(), end=END.isoformat()), timeout=60)
            cov = stub.Coverage(pb.CoverageRequest(calendar=name), timeout=60)
        return (
            [{"date": c.date, "status": c.status, "close_time": c.close_time, "holiday": c.holiday} for c in closes.closes],
            [{"year": y.year, "source": y.source, "kind": y.kind} for y in cov.years],
        )


def run(s: Session, read) -> dict:
    """Compare every calendar. read(name) -> (closes, coverage) from calendar-svc."""
    results = []
    for name in service.CALENDARS:
        closes, coverage = read(name)
        results.append(compare(name, ours(s, name), theirs(closes, coverage)))
    return {"equal": all(r["equal"] for r in results), "calendars": results}
