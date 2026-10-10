"""mkt-data: ISDA's CDS Standard Model calendars, ISDA-NYM and ISDA-TYO (docs/phase-4.md, "Swap curves").

Weekly: mkt-data fetches cdsmodel.com's NYM.csv and TYO.csv, keeps a file raw if it changed, and updates the
calendars' near-raw rows (app/calendars/isda.py). The SPGMI RFR swap curves adjust USD dates on NYM and JPY dates on
TYO. The work runs in the mkt-data container; this DAG only calls its job API (ADR-0031 in nyc_pa_aws_gitops).
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
CALENDARS = ("ISDA-NYM", "ISDA-TYO")


@dag(
    dag_id="mkt_data__isda_calendars",
    schedule="47 11 * * 1",  # Mondays 11:47 UTC, after the FX calendars
    start_date=datetime(2026, 10, 1, tzinfo=UTC),
    catchup=False,
    max_active_runs=1,
    dagrun_timeout=timedelta(minutes=30),
    default_args={"retries": 3, "retry_delay": timedelta(minutes=15)},
    tags=["mkt-data", "calendars", "swaps", "isda"],
    doc_md=__doc__,
)
def isda_calendars():
    @task(outlets=[CALENDAR_SOURCES])
    def capture() -> dict:
        return {name: call_app_job("mkt-data", f"calendars/{name}/capture", timeout=180) for name in CALENDARS}

    capture()


isda_calendars()
