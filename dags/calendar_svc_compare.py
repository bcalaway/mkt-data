"""mkt-data: check calendar-svc's golden calendars against calendar_day (phase 2, step A4).

Daily after calendar-svc's nightly load, and on demand: mkt-data reads
calendar-svc's calendars over gRPC and compares them with its own, every date
1900-2100 and every covered year. The task fails when they differ, so
Grafana's "Airflow task failed" alert emails; the task log has the
differences. Retired with mkt-data's calendar_day when calendars switch over
to calendar-svc (A5).
"""

import sys
from datetime import UTC, datetime, timedelta
from pathlib import Path

from airflow.sdk import dag, task

# The platform's helper lives at Airflow's DAG root (home_platform_jobs.py);
# this repo's dags/ is delivered to dags/mkt-data/ there, so the root is
# one level up. Airflow normally has it on sys.path; this makes sure of it.
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from home_platform_jobs import call_app_job


@dag(
    dag_id="mkt_data__calendar_svc_compare",
    schedule="23 7 * * *",  # daily 07:23 UTC, after calendar-svc's 06:41 load
    start_date=datetime(2026, 10, 1, tzinfo=UTC),
    catchup=False,
    max_active_runs=1,
    dagrun_timeout=timedelta(minutes=20),
    default_args={"retries": 1, "retry_delay": timedelta(minutes=5)},
    tags=["mkt-data", "calendars", "calendar-svc"],
    doc_md=__doc__,
)
def calendar_svc_compare():
    @task
    def compare() -> dict:
        result = call_app_job("mkt-data", "calendars/compare-with-calendar-svc", timeout=300)
        if not result.get("equal"):
            differing = [c["calendar"] for c in result.get("calendars", []) if not c.get("equal")]
            raise ValueError(f"calendar-svc differs from mkt-data's calendar_day for {differing}; see the result above")
        return result

    compare()


calendar_svc_compare()
