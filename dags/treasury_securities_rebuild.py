"""mkt-data: rebuild the Treasury securities sources' near-raw rows from the stored raw captures.

Manual only. Replays every stored capture of each source, oldest first
(`POST /jobs/securities/{source}/rebuild`): records for TD-SECURITIES,
FD-AUCTIONS and FD-MSPD-STRIPS, observations for TD-PRICES and BLS-CPI. No
fetch. Use it after a parser change, or to apply captures taken before their
parser existed (phase 3, step 2: the step 1 captures and the sampling probe's).
One source after another, since each replays its captures in the same
container. Safe to re-run: the result depends only on the stored captures.
No Asset is marked yet: nothing reads these until secmaster-svc (step 3).
"""

import sys
from datetime import UTC, datetime, timedelta
from pathlib import Path

from airflow.sdk import dag, task

# The platform's helper lives at Airflow's DAG root (see treasury_cmt_rebuild.py).
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from home_platform_jobs import call_app_job

SOURCES = ("TD-SECURITIES", "FD-AUCTIONS", "FD-MSPD-STRIPS", "TD-PRICES", "BLS-CPI")


@dag(
    dag_id="mkt_data__treasury_securities_rebuild",
    schedule=None,
    start_date=datetime(2026, 10, 1, tzinfo=UTC),
    catchup=False,
    max_active_runs=1,
    dagrun_timeout=timedelta(hours=2),
    default_args={"retries": 1, "retry_delay": timedelta(minutes=5)},
    tags=["mkt-data", "treasury", "securities", "near-raw"],
    doc_md=__doc__,
)
def treasury_securities_rebuild():
    @task
    def rebuild(source: str) -> dict:
        result = call_app_job("mkt-data", f"securities/{source}/rebuild", timeout=3600)
        print({k: v for k, v in result.items() if k != "parse_failed"})
        for failure in result.get("parse_failed", []):
            print("parse failed:", failure)
        return result

    previous = None
    for source in SOURCES:
        t = rebuild.override(task_id=f"rebuild_{source.lower().replace('-', '_')}")(source)
        if previous is not None:
            previous >> t
        previous = t


treasury_securities_rebuild()
