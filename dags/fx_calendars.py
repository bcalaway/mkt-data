"""mkt-data: the FX futures' delivery-country calendars (docs/phase-4.md, "Calendars").

Weekly: for each calendar, mkt-data fetches its publisher's list where there is
one (gov.uk's bank holidays for GB, the Cabinet Office's national holidays for JP, SIX's SIC holidays for CH), reads its rules files (the cited rules
for older years and the projection to 2100), keeps whatever changed raw, and
updates the calendar's near-raw rows. A calendar that fails doesn't stop the
others; the task fails at the end so Airflow retries. The work runs in the
mkt-data container; this DAG only calls its job API (ADR-0031 in
nyc_pa_aws_gitops).
"""

import sys
from datetime import UTC, datetime, timedelta
from pathlib import Path

from airflow.sdk import Asset, dag, task

# The platform's helper lives at Airflow's DAG root (see nyse_calendar.py).
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from home_platform_jobs import AppJobError, call_app_job

# calendar-svc's load is scheduled on this (as for the other calendars).
CALENDAR_SOURCES = Asset("mkt_data_calendar_sources")
CALENDARS = ("GB", "TARGET", "JP", "CA", "CH", "AU", "NZ")


def capture_all(call=None) -> dict:
    call = call or call_app_job
    out, failed = {}, []
    for name in CALENDARS:
        try:
            out[name] = call("mkt-data", f"calendars/{name}/capture", timeout=180)
        except AppJobError as e:
            print(f"{name}: failed: {str(e)[:300]}")
            failed.append(name)
    if failed:
        raise RuntimeError(f"calendars failed: {failed}")
    return out


@dag(
    dag_id="mkt_data__fx_calendars",
    schedule="41 11 * * 1",  # Mondays 11:41 UTC, after the US and CME calendars
    start_date=datetime(2026, 10, 1, tzinfo=UTC),
    catchup=False,
    max_active_runs=1,
    dagrun_timeout=timedelta(minutes=30),
    default_args={"retries": 3, "retry_delay": timedelta(minutes=15)},
    tags=["mkt-data", "calendars", "futures"],
    doc_md=__doc__,
)
def fx_calendars():
    @task(outlets=[CALENDAR_SOURCES])
    def capture() -> dict:
        return capture_all()

    capture()


fx_calendars()
