"""mkt-data: Federal Reserve holiday calendar (docs/phase-1.md, step 4).

Weekly: mkt-data fetches the Fed's K.8 page, keeps it raw if it changed, and
updates calendar FED (with history). The work runs in the mkt-data
container; this DAG only calls its job API (ADR-0031 in nyc_pa_aws_gitops).
The page changes a few times a year at most, so weekly is plenty; a failed
run retries, and Grafana's "Airflow task failed" alert fires if retries run
out.
"""

import sys
from datetime import UTC, datetime, timedelta
from pathlib import Path

from airflow.sdk import Asset, dag, task

# The platform's helper lives at Airflow's DAG root (home_platform_jobs.py);
# this repo's dags/ is delivered to dags/mkt-data/ there, so the root is
# one level up. Airflow normally has it on sys.path; this makes sure of it.
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from home_platform_jobs import call_app_job

# Marked after each successful run: calendar-svc's load DAG is scheduled on
# this Asset (docs/phase-2.md, Part A), so it rebuilds golden calendars
# from near-raw as soon as a source may have changed.
CALENDAR_SOURCES = Asset("mkt_data_calendar_sources")


@dag(
    dag_id="mkt_data__fed_calendar",
    schedule="17 11 * * 1",  # Mondays 11:17 UTC
    start_date=datetime(2026, 10, 1, tzinfo=UTC),
    catchup=False,
    max_active_runs=1,
    dagrun_timeout=timedelta(minutes=30),
    default_args={"retries": 3, "retry_delay": timedelta(minutes=15)},
    tags=["mkt-data", "calendars"],
    doc_md=__doc__,
)
def fed_calendar():
    @task(outlets=[CALENDAR_SOURCES])
    def capture() -> dict:
        return call_app_job("mkt-data", "calendars/FED/capture", timeout=180)

    capture()


fed_calendar()
