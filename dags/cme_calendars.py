"""mkt-data: CME's business-day calendars, CME-IR and CME-FX (docs/phase-4.md, "Calendars").

Weekly: mkt-data reads its two rules files for each (the cited rules from
1990 and the projection to 2100), keeps a file raw if it changed (a rules
change is a new capture), and updates the calendars' near-raw rows. There's
no page to fetch: CME's terms rule out capturing its holiday pages, so the
rules files cite CME's notices and are extended a year at a time. The work
runs in the mkt-data container; this DAG only calls its job API (ADR-0031 in
nyc_pa_aws_gitops).
"""

import sys
from datetime import UTC, datetime, timedelta
from pathlib import Path

from airflow.sdk import Asset, dag, task

# The platform's helper lives at Airflow's DAG root (see nyse_calendar.py).
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from home_platform_jobs import call_app_job

# calendar-svc's load is scheduled on this (as for the other calendars).
CALENDAR_SOURCES = Asset("mkt_data_calendar_sources")
CALENDARS = ("CME-IR", "CME-FX")


@dag(
    dag_id="mkt_data__cme_calendars",
    schedule="35 11 * * 1",  # Mondays 11:35 UTC, after FED, SIFMA-US and NYSE
    start_date=datetime(2026, 10, 1, tzinfo=UTC),
    catchup=False,
    max_active_runs=1,
    dagrun_timeout=timedelta(minutes=30),
    default_args={"retries": 3, "retry_delay": timedelta(minutes=15)},
    tags=["mkt-data", "calendars", "futures"],
    doc_md=__doc__,
)
def cme_calendars():
    @task(outlets=[CALENDAR_SOURCES])
    def capture() -> dict:
        return {name: call_app_job("mkt-data", f"calendars/{name}/capture", timeout=180) for name in CALENDARS}

    capture()


cme_calendars()
