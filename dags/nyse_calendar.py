"""mkt-data: NYSE holiday calendar (docs/phase-1.md, step 4).

Weekly: mkt-data fetches NYSE's hours and calendars page, keeps the page raw
if it changed, and updates calendar NYSE (full closes, and early closes with
the equities close time) with history. The work runs in the mkt-data
container; this DAG only calls its job API (ADR-0031 in nyc_pa_aws_gitops).
NYSE publishes about three years ahead and rarely changes them, so weekly
is plenty; a failed run retries, and Grafana's "Airflow task failed" alert
fires if retries run out.
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
    dag_id="mkt_data__nyse_calendar",
    schedule="29 11 * * 1",  # Mondays 11:29 UTC, after FED and SIFMA-US
    start_date=datetime(2026, 10, 1, tzinfo=UTC),
    catchup=False,
    max_active_runs=1,
    dagrun_timeout=timedelta(minutes=30),
    default_args={"retries": 3, "retry_delay": timedelta(minutes=15)},
    tags=["mkt-data", "calendars"],
    doc_md=__doc__,
)
def nyse_calendar():
    @task
    def capture() -> dict:
        return call_app_job("mkt-data", "calendars/NYSE/capture", timeout=180)

    capture()


nyse_calendar()
