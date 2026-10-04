"""mkt-data: capture Treasury CMT yields raw (docs/phase-2.md, Part B step 1).

Weekdays in the evening (New York), after Treasury posts the day's par yield
curve (usually by 6 p.m.) and the Fed's H.15 posts the previous day's (4:15
p.m.): mkt-data fetches the current month of each source and keeps it raw if
it changed (one capture per source and month). In the first days of a month
it also re-fetches the previous month, so the last days of the old month and
any late revision land. Kept raw only until step B2 adds the parsers. The work
runs in the mkt-data container; this DAG only calls its job API (ADR-0031 in
nyc_pa_aws_gitops). A failed run retries, and Grafana's "Airflow task failed"
alert fires if retries run out.
"""

import sys
from datetime import UTC, datetime, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo

from airflow.sdk import dag, task

# The platform's helper lives at Airflow's DAG root (home_platform_jobs.py);
# this repo's dags/ is delivered to dags/mkt-data/ there, so the root is
# one level up. Airflow normally has it on sys.path; this makes sure of it.
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from home_platform_jobs import call_app_job

SOURCES = ("UST-PAR", "H15-TCM")


def _periods(now: datetime) -> list[str]:
    """The current month, plus the previous one for the first five days of a month."""
    out = [f"{now.year:04d}-{now.month:02d}"]
    if now.day <= 5:
        prev = now.replace(day=1) - timedelta(days=1)
        out.insert(0, f"{prev.year:04d}-{prev.month:02d}")
    return out


@dag(
    dag_id="mkt_data__treasury_cmt_capture",
    schedule="37 23 * * 1-5",  # weekdays 23:37 UTC (7:37 p.m. EDT, 6:37 p.m. EST)
    start_date=datetime(2026, 10, 1, tzinfo=UTC),
    catchup=False,
    max_active_runs=1,
    dagrun_timeout=timedelta(minutes=30),
    default_args={"retries": 3, "retry_delay": timedelta(minutes=20)},
    tags=["mkt-data", "rates", "treasury"],
    doc_md=__doc__,
)
def treasury_cmt_capture():
    @task
    def capture(source: str) -> list[dict]:
        now = datetime.now(ZoneInfo("America/New_York"))
        return [call_app_job("mkt-data", f"rates/{source}/capture?period={p}", timeout=180) for p in _periods(now)]

    for source in SOURCES:
        capture.override(task_id=f"capture_{source.lower().replace('-', '_')}")(source)


treasury_cmt_capture()
