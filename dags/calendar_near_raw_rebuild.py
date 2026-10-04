"""mkt-data: rebuild the calendars' near-raw rows from raw (docs/phase-2.md, Part A step 1).

Manual only (no schedule). Replays every stored capture of every calendar
source, oldest first, into `source_year` and `source_day`: how near-raw is
first filled from captures taken before it existed, and how a parser fix
reaches a source's whole history. No fetch; the calendars themselves
(`calendar_day`) are untouched. Safe to re-run: the result depends only on
the stored captures. Trigger from the Airflow UI or home-mcp
(`airflow_trigger`).
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

CALENDARS = ("FED", "SIFMA-US", "NYSE")


@dag(
    dag_id="mkt_data__calendar_near_raw_rebuild",
    schedule=None,
    start_date=datetime(2026, 10, 1, tzinfo=UTC),
    catchup=False,
    max_active_runs=1,
    dagrun_timeout=timedelta(minutes=30),
    default_args={"retries": 1, "retry_delay": timedelta(minutes=5)},
    tags=["mkt-data", "calendars", "near-raw"],
    doc_md=__doc__,
)
def calendar_near_raw_rebuild():
    @task(outlets=[CALENDAR_SOURCES])
    def rebuild(calendar: str) -> dict:
        return call_app_job("mkt-data", f"calendars/{calendar}/near-raw/rebuild", timeout=600)

    # One after another: each replays PDFs and pages, and they share the container.
    previous = None
    for calendar in CALENDARS:
        t = rebuild.override(task_id=f"rebuild_{calendar.lower().replace('-', '_')}")(calendar)
        if previous is not None:
            previous >> t
        previous = t


calendar_near_raw_rebuild()
