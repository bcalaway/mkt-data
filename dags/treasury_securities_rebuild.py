"""mkt-data: rebuild the Treasury securities sources' near-raw rows from the stored raw captures.

Manual only. Replays every stored capture of each source, oldest first
(`POST /jobs/securities/{source}/rebuild`): records for TD-SECURITIES,
FD-AUCTIONS and FD-MSPD-STRIPS, observations for TD-PRICES and BLS-CPI. No
fetch. Use it after a parser change, or to apply captures taken before their
parser existed (phase 3, step 2: the step 1 captures and the sampling probe's).
One source after another, since each replays its captures in the same
container. Safe to re-run: the result depends only on the stored captures.
TD-SECURITIES's task marks the Asset `mkt_data_treasury_securities`, so
secmaster-svc's load re-reads the months whose newest capture moved, and
TD-PRICES's marks `mkt_data_treasury_prices`, so quote-svc's load re-reads
the days whose newest capture moved.
"""

import sys
from datetime import UTC, datetime, timedelta
from pathlib import Path

from airflow.sdk import Asset, dag, task

# The platform's helper lives at Airflow's DAG root (see treasury_cmt_rebuild.py).
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from home_platform_jobs import call_app_job

SOURCES = ("TD-SECURITIES", "FD-AUCTIONS", "FD-MSPD-STRIPS", "TD-PRICES", "BLS-CPI")
# secmaster-svc's load is scheduled on this (see treasury_securities_capture.py).
TREASURY_SECURITIES = Asset("mkt_data_treasury_securities")
# quote-svc's load is scheduled on this.
TREASURY_PRICES = Asset("mkt_data_treasury_prices")


def rebuild_source(source: str) -> dict:
    result = call_app_job("mkt-data", f"securities/{source}/rebuild", timeout=3600)
    print({k: v for k, v in result.items() if k != "parse_failed"})
    for failure in result.get("parse_failed", []):
        print("parse failed:", failure)
    return result


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
    @task(outlets=[TREASURY_SECURITIES])
    def rebuild_and_mark(source: str) -> dict:
        """TD-SECURITIES: rebuilt, then the Asset is marked, so secmaster-svc re-reads the months that moved."""
        return rebuild_source(source)

    @task(outlets=[TREASURY_PRICES])
    def rebuild_and_mark_prices(source: str) -> dict:
        """TD-PRICES: rebuilt, then the Asset is marked, so quote-svc re-reads the days that moved."""
        return rebuild_source(source)

    @task
    def rebuild(source: str) -> dict:
        return rebuild_source(source)

    previous = None
    for source in SOURCES:
        step = {"TD-SECURITIES": rebuild_and_mark, "TD-PRICES": rebuild_and_mark_prices}.get(source, rebuild)
        t = step.override(task_id=f"rebuild_{source.lower().replace('-', '_')}")(source)
        if previous is not None:
            previous >> t
        previous = t


treasury_securities_rebuild()
