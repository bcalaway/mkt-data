"""mkt-data: rebuild Treasury CMT observations from the stored raw captures.

Manual only. Replays every stored capture of UST-PAR and H15-TCM, oldest
first, into near-raw observations (`POST /jobs/rates/{source}/rebuild`): no
fetch. Use it after a parser fix, so the whole history gets it (the 2010-10
Treasury file, whose Columbus Day entry has no values, was the first). Marks
the Asset `mkt_data_cmt_observations`, so quote-svc reloads the months whose
newest capture moved. Safe to re-run: the result depends only on the stored
captures.
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

SOURCES = ("UST-PAR", "H15-TCM")
CMT_OBSERVATIONS = Asset("mkt_data_cmt_observations")


@dag(
    dag_id="mkt_data__treasury_cmt_rebuild",
    schedule=None,
    start_date=datetime(2026, 10, 1, tzinfo=UTC),
    catchup=False,
    max_active_runs=1,
    dagrun_timeout=timedelta(hours=1),
    default_args={"retries": 1, "retry_delay": timedelta(minutes=5)},
    tags=["mkt-data", "rates", "treasury", "near-raw"],
    doc_md=__doc__,
)
def treasury_cmt_rebuild():
    @task(outlets=[CMT_OBSERVATIONS])
    def rebuild(source: str) -> dict:
        return call_app_job("mkt-data", f"rates/{source}/rebuild", timeout=1800)

    # One after the other: each replays hundreds of captures in the same container.
    previous = None
    for source in SOURCES:
        t = rebuild.override(task_id=f"rebuild_{source.lower().replace('-', '_')}")(source)
        if previous is not None:
            previous >> t
        previous = t


treasury_cmt_rebuild()
