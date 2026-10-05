"""mkt-data: backfill Treasury CMT history, a month at a time (docs/phase-2.md, Part B step 6).

Manual only. Captures every month of UST-PAR (Treasury's par yield curve,
from 1990-01) and H15-TCM (the Fed's H.15, from 1962-01) between `start` and
`end` through the same job the daily DAG uses (`POST
/jobs/rates/{source}/capture?period=`), so each month is one raw capture,
parsed into near-raw observations. One year runs at a time, months in
order, with a pause between requests to be polite to treasury.gov and
federalreserve.gov: about 1,200 months take roughly an hour.

Safe to re-run: a month already captured with the same content is
"unchanged" and adds nothing. A month that fails (fetch or parse) is listed
and the backfill carries on; the last task fails if any did, so they're
visible, and re-running retries just those cheaply. It marks the Asset
`mkt_data_cmt_observations` at the end, so quote-svc loads everything.

Trigger it from the Airflow UI with the defaults (both sources, full
history to last month), or narrow it with the params.
"""

import re
import sys
import time
from datetime import UTC, datetime, timedelta
from pathlib import Path

from airflow.sdk import Asset, Param, dag, get_current_context, task

# The platform's helper lives at Airflow's DAG root (home_platform_jobs.py);
# this repo's dags/ is delivered to dags/mkt-data/ there, so the root is
# one level up. Airflow normally has it on sys.path; this makes sure of it.
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from home_platform_jobs import AppJobError, call_app_job

FIRST = {"UST-PAR": "1990-01", "H15-TCM": "1962-01"}
PAUSE_SECONDS = 2
CMT_OBSERVATIONS = Asset("mkt_data_cmt_observations")


def months(start: str, end: str) -> list[str]:
    y, m = (int(x) for x in start.split("-"))
    ey, em = (int(x) for x in end.split("-"))
    out = []
    while (y, m) <= (ey, em):
        out.append(f"{y:04d}-{m:02d}")
        y, m = (y + 1, 1) if m == 12 else (y, m + 1)
    return out


def last_month(now: datetime) -> str:
    prev = now.replace(day=1) - timedelta(days=1)
    return f"{prev.year:04d}-{prev.month:02d}"


def month_param(value, name: str) -> str:
    """A YYYY-MM month from a param: "" or None for unset; also takes YYYY-M, YYYY-MM-DD and YYYY/MM."""
    v = str(value or "").strip().replace("/", "-")
    if not v:
        return ""
    m = re.fullmatch(r"(\d{4})-(\d{1,2})(-\d{1,2})?", v)
    if not m or not 1 <= int(m.group(2)) <= 12:
        raise ValueError(f"{name} {value!r} isn't a month like 1990-01")
    return f"{int(m.group(1)):04d}-{int(m.group(2)):02d}"


def plan_batches(source: str, start: str, end: str, now: datetime) -> list[dict]:
    """One batch per source and year, oldest first. Raises ValueError when there's nothing to do."""
    if source not in (*FIRST, "both"):
        raise ValueError(f"source {source!r} isn't one of both, {', '.join(FIRST)}")
    start, end = month_param(start, "start"), month_param(end, "end")
    sources = list(FIRST) if source == "both" else [source]
    end = end or last_month(now)
    batches = []
    for src in sources:
        lo = max(start, FIRST[src]) if start else FIRST[src]
        by_year: dict[str, list[str]] = {}
        for p in months(lo, end):
            by_year.setdefault(p[:4], []).append(p)
        batches += [{"source": src, "year": y, "periods": ps} for y, ps in sorted(by_year.items())]
    if not batches:
        raise ValueError(f"nothing to capture: start {start or '(first month)'} is after end {end}")
    return batches


@dag(
    dag_id="mkt_data__treasury_cmt_backfill",
    schedule=None,
    start_date=datetime(2026, 10, 1, tzinfo=UTC),
    catchup=False,
    max_active_runs=1,
    dagrun_timeout=timedelta(hours=6),
    default_args={"retries": 1, "retry_delay": timedelta(minutes=5)},
    params={
        "source": Param("both", enum=["both", "UST-PAR", "H15-TCM"]),
        "start": Param("", type="string", description="YYYY-MM; empty for each source's first month"),
        "end": Param("", type="string", description="YYYY-MM; empty for last month"),
    },
    tags=["mkt-data", "rates", "treasury", "backfill"],
    doc_md=__doc__,
)
def treasury_cmt_backfill():
    @task
    def plan() -> list[dict]:
        p = get_current_context()["params"]
        print(f"params: source={p.get('source')!r} start={p.get('start')!r} end={p.get('end')!r}")
        batches = plan_batches(p.get("source") or "both", p.get("start"), p.get("end"), datetime.now(UTC))
        print(f"plan: {len(batches)} source-years, {sum(len(b['periods']) for b in batches)} months, "
              f"{batches[0]['source']} {batches[0]['periods'][0]} to {batches[-1]['source']} {batches[-1]['periods'][-1]}")
        return batches

    @task(max_active_tis_per_dagrun=1)
    def capture_year(batch: dict) -> dict:
        out = {"source": batch["source"], "year": batch["year"], "new": 0, "unchanged": 0, "values": 0, "failed": []}
        for period in batch["periods"]:
            try:
                r = call_app_job("mkt-data", f"rates/{batch['source']}/capture?period={period}", timeout=180)
                out["new" if r.get("new_capture") else "unchanged"] += 1
                out["values"] += r.get("values", 0)
            except AppJobError as e:
                out["failed"].append({"period": period, "error": str(e)[:300]})
            time.sleep(PAUSE_SECONDS)
        return out

    @task(outlets=[CMT_OBSERVATIONS], trigger_rule="all_done")
    def report(results: list[dict]) -> dict:
        failed = [f | {"source": r["source"]} for r in results for f in r["failed"]]
        summary = {
            "years": len(results),
            "new_captures": sum(r["new"] for r in results),
            "unchanged": sum(r["unchanged"] for r in results),
            "failed": failed,
        }
        print(summary)
        if failed:
            raise RuntimeError(f"{len(failed)} month(s) failed; re-run to retry them: {failed[:10]}")
        return summary

    report(capture_year.expand(batch=plan()))


treasury_cmt_backfill()
