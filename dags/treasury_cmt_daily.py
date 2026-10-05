"""mkt-data: the daily Treasury CMT captures (docs/phase-2.md, Part B step 7).

Two DAGs, one per source, each on its publisher's schedule (New York time):

- `mkt_data__ust_par`: Treasury's par yield curve, weekdays from 6:30 p.m.
  Treasury posts the day's curve on SIFMA-US business days, usually by 6 p.m.
- `mkt_data__h15_tcm`: the Fed's H.15, weekdays from 4:30 p.m. H.15 is
  released at 4:15 p.m. on Fed business days with the previous SIFMA-US
  business day's yields.

Each run:

1. **Is there a release today?** It asks calendar-svc (UST-PAR: SIFMA-US;
   H15-TCM: FED). On a holiday the run stops here and the rest is skipped.
   If calendar-svc can't answer, the run goes ahead: a capture on a holiday
   only comes back unchanged.
2. **Capture** the current month (and the previous one in a month's first five
   days, so late days and revisions land), then check that the expected day
   is in: today for UST-PAR; for H15-TCM the SIFMA-US business day before
   today. If it isn't yet, the task fails and retries every 30 minutes until
   about 10 p.m.; after that Grafana's "Airflow task failed" alert fires. A
   failed fetch (the Fed's download service often answers an empty body) is
   tried again after 10, 30 and 60 seconds first, within the task.
3. **Mark** the Asset `mkt_data_cmt_observations` only if the capture added,
   changed or removed an observation, so quote-svc's load (scheduled on it)
   runs when there's something new.

The work runs in the mkt-data container; these DAGs only call job APIs
(ADR-0031 in nyc_pa_aws_gitops). New DAGs start paused.
"""

import sys
import time
from datetime import UTC, date, datetime, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo

from airflow.sdk import Asset, CronTriggerTimetable, dag, task

try:
    from airflow.sdk.exceptions import AirflowSkipException
except ImportError:  # older Task SDKs
    from airflow.exceptions import AirflowSkipException

# The platform's helper lives at Airflow's DAG root (home_platform_jobs.py);
# this repo's dags/ is delivered to dags/mkt-data/ there, so the root is
# one level up. Airflow normally has it on sys.path; this makes sure of it.
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from home_platform_jobs import AppJobError, call_app_job

NEW_YORK = ZoneInfo("America/New_York")
# quote-svc's load DAG (quote_svc__load) is scheduled on this.
CMT_OBSERVATIONS = Asset("mkt_data_cmt_observations")
RETRY_DELAY = timedelta(minutes=30)
# A fetch that fails (HTTP 502 from the job: the Fed's download service answers
# about half of quick requests with an empty body) is tried again after these
# pauses within the task, rather than waiting 30 minutes for the task's retry.
FETCH_PAUSES = (10, 30, 60)
LOOKBACK_DAYS = 10  # far enough back to pass any run of closes


def periods(today: date) -> list[str]:
    """The current month, plus the previous one for the first five days of a month."""
    out = [f"{today:%Y-%m}"]
    if today.day <= 5:
        out.insert(0, f"{today.replace(day=1) - timedelta(days=1):%Y-%m}")
    return out


def business_day(calendar: str, day: date, call=None) -> bool | None:
    """calendar-svc's answer for one day: True, False, or None if it couldn't answer."""
    call = call or call_app_job
    try:
        r = call("calendar-svc", f"calendars/{calendar}/business-day", {"on": day.isoformat()}, method="GET")
    except AppJobError as e:
        print(f"calendar-svc couldn't say whether {day} is a {calendar} business day: {e}")
        return None
    print(f"{calendar} {day}: {r.get('status')}{' (projected)' if r.get('projected') else ''}")
    return bool(r["business_day"])


def previous_business_day(calendar: str, today: date, call=None) -> date:
    """The last business day before today; the previous weekday if calendar-svc can't say."""
    for n in range(1, LOOKBACK_DAYS + 1):
        day = today - timedelta(days=n)
        if day.weekday() >= 5:
            continue
        answer = business_day(calendar, day, call)
        if answer is None:
            break
        if answer:
            return day
    day = today - timedelta(days=1)
    while day.weekday() >= 5:
        day -= timedelta(days=1)
    return day


def capture_month(source: str, period: str, call=None, sleep=time.sleep) -> dict:
    """One capture job call, retried on HTTP 502 (a failed fetch); other errors raise at once."""
    call = call or call_app_job
    for pause in (*FETCH_PAUSES, None):
        try:
            return call("mkt-data", f"rates/{source}/capture?period={period}", timeout=180)
        except AppJobError as e:
            if pause is None or "HTTP 502" not in str(e):
                raise
            print(f"{source} {period}: fetch failed, trying again in {pause} s: {str(e)[:200]}")
            sleep(pause)
    raise AssertionError("unreachable")


def landed(results: list[dict], expected: date) -> bool:
    """Whether any captured month now has a value for the expected day (or later)."""
    return any((r.get("last_date") or "") >= expected.isoformat() for r in results)


def changed(results: list[dict]) -> bool:
    return any(r.get("added") or r.get("changed") or r.get("removed") for r in results)


def _tasks(source: str, release_calendar: str, retries: int, expected_day) -> None:
    """The three tasks, wired inside a DAG: release check, capture, mark."""

    @task.short_circuit
    def release_today() -> bool:
        today = datetime.now(NEW_YORK).date()
        return business_day(release_calendar, today) is not False

    @task(retries=retries, retry_delay=RETRY_DELAY)
    def capture() -> list[dict]:
        today = datetime.now(NEW_YORK).date()
        want = expected_day(today)
        results = [capture_month(source, p) for p in periods(today)]
        for r in results:
            print({k: r.get(k) for k in ("period", "new_capture", "values", "last_date", "added", "changed", "removed")})
        if not landed(results, want):
            raise RuntimeError(f"{source} has no values for {want} yet; retrying in {RETRY_DELAY}")
        return results

    @task(outlets=[CMT_OBSERVATIONS])
    def mark(results: list[dict]) -> str:
        if not changed(results):
            raise AirflowSkipException("nothing new: quote-svc has nothing to load")
        return "marked"

    got = capture()
    release_today() >> got
    mark(got)


DAG_ARGS = {
    "start_date": datetime(2026, 10, 1, tzinfo=UTC),
    "catchup": False,
    "max_active_runs": 1,
    "dagrun_timeout": timedelta(hours=6),
    "tags": ["mkt-data", "rates", "treasury"],
    "doc_md": __doc__,
}


@dag(dag_id="mkt_data__ust_par", schedule=CronTriggerTimetable("30 18 * * 1-5", timezone="America/New_York"),
     **DAG_ARGS)
def ust_par():
    # Treasury posts today's curve on SIFMA-US business days. 6:30 p.m., then every 30 minutes to 10:00 p.m.
    _tasks("UST-PAR", "SIFMA-US", retries=7, expected_day=lambda today: today)


@dag(dag_id="mkt_data__h15_tcm", schedule=CronTriggerTimetable("30 16 * * 1-5", timezone="America/New_York"),
     **DAG_ARGS)
def h15_tcm():
    # H.15 comes out on Fed business days with the previous SIFMA-US business day's yields.
    # 4:30 p.m., then every 30 minutes to 10:00 p.m.
    _tasks("H15-TCM", "FED", retries=11, expected_day=lambda today: previous_business_day("SIFMA-US", today))


ust_par()
h15_tcm()
