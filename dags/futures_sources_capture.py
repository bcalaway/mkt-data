"""mkt-data: the daily captures of phase 4's sources (docs/phase-4.md, steps 1 and 6).

Each source's parsed observations reach quote-svc through an Asset: a capture
that added, changed or removed observations marks `mkt_data_fixings` (the
New York Fed's, H.10's and the ECB's) or `mkt_data_positioning` (the CFTC's),
and quote-svc's load runs on them (step 6). NYFED-SOFR-AVG is kept raw and
marks nothing.

One DAG, weekdays at 7:45 p.m. New York time, one task per source so a
failing source doesn't hold up the others:

- NYFED-SOFR, NYFED-EFFR, NYFED-SOFR-AVG, FRB-H10 and FRB-H10-RATES, ECB-EXR: the months of
  the last ten days up to yesterday (the New York Fed publishes a day's rates
  the next morning, H.10 comes out weekly on Mondays), so a month is
  re-fetched for ten days after it ends and a revision is caught.
- CFTC-TFF and CFTC-TFF-COMBINED: the report dates (Tuesdays) of the last
  two reports due out by today (a report is due the Friday after its
  Tuesday), so a report published late, the Monday after a holiday, is
  picked up that evening. When the Tuesday is a federal holiday the CFTC
  dates the report the Monday before (2025-11-10 for Veterans Day,
  2023-07-03, the Christmas and New Year weeks), so that week asks for the
  Monday too (step 6).

A period with nothing published yet (NOT_PUBLISHED from the job) is logged,
not a failure: the next evening asks again.

A failed fetch (HTTP 502 from the job) is tried again after 10, 30 and 60
seconds within the task, then the task retries once an hour later. The work
runs in the mkt-data container; this DAG only calls its job API (ADR-0031 in
nyc_pa_aws_gitops). New DAGs start paused.

A second, manual DAG, `mkt_data__futures_sources_probe`, captures the
periods given in its form for one source, for fixtures and history depth.
Run with the form left as it is (source "all", no periods), it samples one
period a year from each source's earliest plausible year to now and logs
each period's size, so a source's first year shows where the answers start.
"""

import sys
import time
from datetime import UTC, date, datetime, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo

try:  # Airflow 3's home for it; 2.x's as a fallback (see treasury_cmt_daily.py)
    from airflow.sdk.exceptions import AirflowSkipException
except ImportError:
    from airflow.exceptions import AirflowSkipException
from airflow.sdk import Asset, CronTriggerTimetable, Param, dag, get_current_context, task

# The platform's helper lives at Airflow's DAG root (see treasury_cmt_daily.py).
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from home_platform_jobs import AppJobError, call_app_job

# What quote-svc's load runs on (its dags/load.py): marked only when a capture changed observations.
FIXINGS = Asset("mkt_data_fixings")
POSITIONING = Asset("mkt_data_positioning")

NEW_YORK = ZoneInfo("America/New_York")
FETCH_PAUSES = (10, 30, 60)
MONTH_DAYS_BACK = 10  # a month is re-fetched until this many days after it ends
CFTC_REPORTS = 2  # the latest reports due, re-fetched each evening
# What mkt-data says when a period has nothing published yet (app/futures/sources.py): logged, not a failure.
NOT_PUBLISHED = "NOT_PUBLISHED"

MONTHLY = ("NYFED-SOFR", "NYFED-EFFR", "NYFED-SOFR-AVG", "FRB-H10", "FRB-H10-RATES", "ECB-EXR")
WEEKLY = ("CFTC-TFF", "CFTC-TFF-COMBINED")
SOURCES = MONTHLY + WEEKLY
# The Asset each source's new observations mark; none for a source kept raw.
MARKS = {**dict.fromkeys(("NYFED-SOFR", "NYFED-EFFR", "FRB-H10", "FRB-H10-RATES", "ECB-EXR"), FIXINGS),
         **dict.fromkeys(WEEKLY, POSITIONING)}


def recent_months(today: date, back: int = MONTH_DAYS_BACK) -> list[str]:
    """The months of the days from `back` days ago to yesterday, oldest first."""
    out = []
    for n in range(back, 0, -1):
        m = f"{today - timedelta(days=n):%Y-%m}"
        if m not in out:
            out.append(m)
    return out


def cftc_report_dates(today: date, n: int = CFTC_REPORTS) -> list[str]:
    """The `n` latest Tuesdays whose report was due (the Friday after) by today, oldest first."""
    friday = today - timedelta(days=(today.weekday() - 4) % 7)  # the latest Friday on or before today
    tuesdays = [friday - timedelta(days=3 + 7 * k) for k in range(n)]
    return [d.isoformat() for d in reversed(tuesdays)]


def fed_business_day(day: date, call=None) -> bool | None:
    """calendar-svc's FED answer for a day: True, False, or None if it couldn't say."""
    call = call or call_app_job
    try:
        r = call("calendar-svc", "calendars/FED/business-day", {"on": day.isoformat()}, method="GET")
    except AppJobError as e:
        print(f"calendar-svc couldn't say whether {day} is a FED business day: {e}")
        return None
    return bool(r["business_day"])


def with_holiday_mondays(tuesdays: list[str], is_business_day=fed_business_day) -> list[str]:
    """Each report date, preceded by its Monday when the Tuesday is a federal holiday (the CFTC dates that week's
    report the Monday). If calendar-svc can't say, the Monday is asked for too: an empty answer costs nothing."""
    out = []
    for t in tuesdays:
        day = date.fromisoformat(t)
        if is_business_day(day) is not True:
            out.append((day - timedelta(days=1)).isoformat())
        out.append(t)
    return out


def periods_for(source: str, today: date, is_business_day=fed_business_day) -> list[str]:
    if source in MONTHLY:
        return recent_months(today)
    if source in WEEKLY:
        return with_holiday_mondays(cftc_report_dates(today), is_business_day)
    raise ValueError(f"unknown source {source}")


def changed(results: list[dict]) -> bool:
    return any(r.get("added") or r.get("changed") or r.get("removed") for r in results)


def capture(source: str, period: str, call=None, sleep=time.sleep) -> dict:
    """One capture job call, retried on HTTP 502 (a failed fetch); other errors, and NOT_PUBLISHED, raise at once."""
    call = call or call_app_job
    for pause in (*FETCH_PAUSES, None):
        try:
            return call("mkt-data", f"futures/{source}/capture?period={period}", timeout=180)
        except AppJobError as e:
            if pause is None or "HTTP 502" not in str(e) or NOT_PUBLISHED in str(e):
                raise
            print(f"{source} {period}: fetch failed, trying again in {pause} s: {str(e)[:200]}")
            sleep(pause)
    raise AssertionError("unreachable")


def capture_all(source: str, periods: list[str], call=None, sleep=time.sleep) -> list[dict]:
    """Capture every period; report each, then fail if any failed (after trying them all)."""
    results, failed = [], []
    for p in periods:
        try:
            r = capture(source, p, call, sleep)
        except AppJobError as e:
            if NOT_PUBLISHED in str(e):
                print(f"{source} {p}: nothing published yet, the next capture asks again")
                continue
            print(f"{source} {p}: failed: {str(e)[:300]}")
            failed.append(p)
            continue
        print({k: r.get(k) for k in ("period", "capture_id", "new_capture", "size_bytes", "content_type")})
        results.append(r)
    if failed:
        raise RuntimeError(f"{source}: {len(failed)} of {len(periods)} periods failed: {failed}")
    return results


@dag(
    dag_id="mkt_data__futures_sources_capture",
    schedule=CronTriggerTimetable("45 19 * * 1-5", timezone="America/New_York"),
    start_date=datetime(2026, 10, 1, tzinfo=UTC),
    catchup=False,
    max_active_runs=1,
    dagrun_timeout=timedelta(hours=3),
    tags=["mkt-data", "futures", "fixings", "cftc"],
    doc_md=__doc__,
)
def futures_sources_capture():
    for source in SOURCES:
        slug = source.lower().replace("-", "_")

        @task(task_id=f"capture_{slug}", retries=1, retry_delay=timedelta(hours=1))
        def run(source: str = source) -> list[dict]:
            return capture_all(source, periods_for(source, datetime.now(NEW_YORK).date()))

        got = run()
        if source in MARKS:

            @task(task_id=f"mark_{slug}", outlets=[MARKS[source]])
            def mark(results: list[dict], source: str = source) -> str:
                if not changed(results):
                    raise AirflowSkipException(f"{source}: nothing new for quote-svc")
                return "marked"

            mark(got)


futures_sources_capture()


# The first year to sample for each source's history depth: before its known or plausible start.
# Never before the source's first_period in app/futures/sources.py (the job refuses a period before it).
SAMPLE_FROM = {"NYFED-SOFR": 2018, "NYFED-EFFR": 2000, "NYFED-SOFR-AVG": 2020, "FRB-H10": 2006, "FRB-H10-RATES": 1971,
               "ECB-EXR": 1999, "CFTC-TFF": 2006, "CFTC-TFF-COMBINED": 2006}


def sample_periods(source: str, today: date) -> list[str]:
    """One period a year: June's month (every source publishes in June), or the CFTC's report of the third Tuesday
    of June."""
    out = []
    for year in range(SAMPLE_FROM[source], today.year + 1):
        if source in WEEKLY:
            june1 = date(year, 6, 1)
            day = june1 + timedelta(days=(1 - june1.weekday()) % 7 + 14)
            if day + timedelta(days=3) <= today:
                out.append(day.isoformat())
        elif date(year, 7, 1) <= today:
            out.append(f"{year}-06")
    return out


def parse_periods(text: str) -> list[str]:
    """Periods from the probe form: comma- or space-separated, in the order given, duplicates dropped."""
    out = []
    for p in text.replace(",", " ").split():
        if p not in out:
            out.append(p)
    return out


@dag(
    dag_id="mkt_data__futures_sources_probe",
    schedule=None,
    start_date=datetime(2026, 10, 1, tzinfo=UTC),
    catchup=False,
    max_active_runs=1,
    tags=["mkt-data", "futures", "fixings", "cftc"],
    doc_md=__doc__,
    params={
        "source": Param("all", enum=["all", *SOURCES]),
        "periods": Param("", type="string",
                         description="Comma-separated: YYYY-MM (the New York Fed, H.10 and ECB sources) or "
                                     "YYYY-MM-DD, a report's Tuesday (the CFTC sources). Empty: one sample a year"),
    },
)
def futures_sources_probe():
    @task
    def probe() -> dict:
        p = get_current_context()["params"]
        periods = parse_periods(p.get("periods") or "")
        source = p.get("source") or "all"
        if periods:
            if source == "all":
                raise ValueError("periods need a single source")
            return {source: capture_all(source, periods)}
        today = datetime.now(NEW_YORK).date()
        report, failed = {}, []
        for name in (SOURCES if source == "all" else [source]):
            try:
                report[name] = capture_all(name, sample_periods(name, today))
            except RuntimeError as e:  # some periods failed: logged above; carry on with the next source
                failed.append(str(e))
        if failed:
            raise RuntimeError("; ".join(failed))
        return report

    probe()


futures_sources_probe()
