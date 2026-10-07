"""mkt-data: backfill the Treasury securities sources, a year at a time (docs/phase-3.md, step 5).

Manual only. Captures every period of each source between `start` and `end`
through the same job the daily DAG uses (`POST
/jobs/securities/{source}/capture?period=`), so each period is one raw
capture, parsed into near-raw records or observations:

- TD-SECURITIES and FD-AUCTIONS: each month of auctions from 1980-01;
- FD-MSPD-STRIPS: each month-end from 2001-01;
- TD-PRICES: each SIFMA-US business day from 2008-01-02 (calendar-svc's
  closes, a year at a time; weekdays if it can't answer). FedInvest answers
  an empty page before its first day, which parses to no prices.

BLS-CPI isn't here: its 25 keyless requests a day go through the probe DAG.

One source-year runs at a time, oldest first, sources in the order above (so
the securities are in before their prices, though quote-svc doesn't need
that: a day with CUSIPs it couldn't map is reloaded once it can), with a
pause between requests to be a polite client of TreasuryDirect and Fiscal
Data. FedInvest took 2.6 s a day without the pause (21 days on 2026-10-07),
so its ~4,700 days take about four and a half hours with it; the securities
months about an hour.

Each finished year marks the Assets `mkt_data_treasury_securities` and
`mkt_data_treasury_prices`, so secmaster-svc's and quote-svc's loads keep
up a year at a time instead of reading the whole history at the end.

Safe to re-run: a period already captured with the same content is
"unchanged" and adds nothing (it's parsed again, so a parser fix reaches it).
A fetch that fails is tried again after 10, 30 and 60 seconds; a period that
still fails is listed and the backfill carries on. The last task fails if
any did, and re-running retries just those cheaply.

Trigger it from the Airflow UI (or home-mcp's airflow_trigger) with the
defaults (every source, full history), or narrow it with the params.
"""

import re
import sys
import time
from datetime import UTC, date, datetime, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo

from airflow.sdk import Asset, Param, dag, get_current_context, task

# The platform's helper lives at Airflow's DAG root (see treasury_cmt_backfill.py).
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from home_platform_jobs import AppJobError, call_app_job

NEW_YORK = ZoneInfo("America/New_York")
# Each source's first period (TreasuryDirect's and Fiscal Data's auctions start in
# 1980; MSPD's STRIPS table in 2001; FedInvest's prices between 2008-01-09 and
# 2009-01-14, so from the first business day of 2008: the empty days cost little).
FIRST = {"TD-SECURITIES": "1980-01", "FD-AUCTIONS": "1980-01", "FD-MSPD-STRIPS": "2001-01", "TD-PRICES": "2008-01-02"}
DAILY = {"TD-PRICES"}
CALENDAR = "SIFMA-US"
PAUSE_SECONDS = 1
FETCH_PAUSES = (10, 30, 60)
TREASURY_SECURITIES = Asset("mkt_data_treasury_securities")
TREASURY_PRICES = Asset("mkt_data_treasury_prices")


def capture(source: str, period: str, call=None, sleep=time.sleep) -> dict:
    """One capture job call, retried on HTTP 502 (a failed fetch); other errors raise at once."""
    call = call or call_app_job
    for pause in (*FETCH_PAUSES, None):
        try:
            return call("mkt-data", f"securities/{source}/capture?period={period}", timeout=180)
        except AppJobError as e:
            if pause is None or "HTTP 502" not in str(e):
                raise
            sleep(pause)
    raise AssertionError("unreachable")


def months(start: str, end: str) -> list[str]:
    y, m = (int(x) for x in start.split("-"))
    ey, em = (int(x) for x in end.split("-"))
    out = []
    while (y, m) <= (ey, em):
        out.append(f"{y:04d}-{m:02d}")
        y, m = (y + 1, 1) if m == 12 else (y, m + 1)
    return out


def closed_days(year: int, call=None) -> set[date] | None:
    """SIFMA-US's closed days in a year, from calendar-svc; None if it couldn't answer."""
    call = call or call_app_job
    try:
        r = call("calendar-svc", f"calendars/{CALENDAR}/closes",
                 {"start": f"{year}-01-01", "end": f"{year}-12-31", "limit": "5000"}, method="GET")
    except AppJobError as e:
        print(f"calendar-svc couldn't list {CALENDAR}'s {year} closes ({e}); weekdays stand in")
        return None
    return {date.fromisoformat(c["date"]) for c in r["closes"] if c.get("status") == "closed"}


def business_days(start: date, end: date, closed: set[date]) -> list[str]:
    out, d = [], start
    while d <= end:
        if d.weekday() < 5 and d not in closed:
            out.append(d.isoformat())
        d += timedelta(days=1)
    return out


def period_param(value, name: str, daily: bool) -> str:
    """A month (YYYY-MM) or, for a daily source, a day (YYYY-MM-DD) from a param; "" for unset."""
    v = str(value or "").strip().replace("/", "-")
    if not v:
        return ""
    m = re.fullmatch(r"(\d{4})-(\d{1,2})(?:-(\d{1,2}))?", v)
    if not m or not 1 <= int(m.group(2)) <= 12:
        raise ValueError(f"{name} {value!r} isn't a month like 1990-01 or a day like 2010-06-30")
    y, mo = int(m.group(1)), int(m.group(2))
    if not daily:
        return f"{y:04d}-{mo:02d}"
    if m.group(3):
        return date(y, mo, int(m.group(3))).isoformat()
    # A bare month for a daily source: its first day for start, its last for end.
    if name == "end":
        nxt = date(y + (mo == 12), mo % 12 + 1, 1)
        return (nxt - timedelta(days=1)).isoformat()
    return date(y, mo, 1).isoformat()


def plan_batches(source: str, start, end, now: datetime, closes=closed_days) -> list[dict]:
    """One batch per source and year, oldest first. Raises ValueError when there's nothing to do."""
    if source not in (*FIRST, "all"):
        raise ValueError(f"source {source!r} isn't one of all, {', '.join(FIRST)}")
    today = now.astimezone(NEW_YORK).date()
    sources = list(FIRST) if source == "all" else [source]
    batches = []
    for src in sources:
        daily = src in DAILY
        lo, hi = period_param(start, "start", daily), period_param(end, "end", daily)
        lo = max(lo, FIRST[src]) if lo else FIRST[src]
        if daily:
            # Up to yesterday: the daily capture DAG has today and the previous business day.
            hi = min(hi, (today - timedelta(days=1)).isoformat()) if hi else (today - timedelta(days=1)).isoformat()
            first, last = date.fromisoformat(lo), date.fromisoformat(hi)
            for y in range(first.year, last.year + 1):
                closed = closes(y)
                days = business_days(max(first, date(y, 1, 1)), min(last, date(y, 12, 31)), closed or set())
                if days:
                    batches.append({"source": src, "year": str(y), "periods": days,
                                    "calendar": CALENDAR if closed is not None else "weekdays"})
        else:
            # Up to last month: the daily capture DAG has this month (and next, for announcements).
            prev = f"{today.replace(day=1) - timedelta(days=1):%Y-%m}"
            hi = min(hi, prev) if hi else prev
            by_year: dict[str, list[str]] = {}
            for p in months(lo, hi) if lo <= hi else []:
                by_year.setdefault(p[:4], []).append(p)
            batches += [{"source": src, "year": y, "periods": ps} for y, ps in sorted(by_year.items())]
    if not batches:
        raise ValueError(f"nothing to capture for {source} between {start or '(first)'} and {end or '(latest)'}")
    return batches


def capture_batch(batch: dict, call=None, sleep=time.sleep) -> dict:
    """Every period of one source-year; failures are listed, not raised."""
    out = {"source": batch["source"], "year": batch["year"], "periods": len(batch["periods"]), "new": 0,
           "unchanged": 0, "values": 0, "records": 0, "empty": 0, "failed": []}
    for period in batch["periods"]:
        try:
            r = capture(batch["source"], period, call, sleep)
            out["new" if r.get("new_capture") else "unchanged"] += 1
            out["values"] += r.get("values", 0) or 0
            out["records"] += r.get("records", 0) or 0
            if not (r.get("values") or r.get("records")):
                out["empty"] += 1
        except AppJobError as e:
            out["failed"].append({"period": period, "error": str(e)[:300]})
        sleep(PAUSE_SECONDS)
    return out


@dag(
    dag_id="mkt_data__treasury_securities_backfill",
    schedule=None,
    start_date=datetime(2026, 10, 1, tzinfo=UTC),
    catchup=False,
    max_active_runs=1,
    dagrun_timeout=timedelta(hours=12),
    default_args={"retries": 1, "retry_delay": timedelta(minutes=5)},
    params={
        "source": Param("all", enum=["all", *FIRST]),
        # Optional: Airflow's form won't submit an empty plain-string param.
        "start": Param(None, type=["null", "string"],
                       description="YYYY-MM (YYYY-MM-DD for TD-PRICES); empty for each source's first period"),
        "end": Param(None, type=["null", "string"],
                     description="YYYY-MM (YYYY-MM-DD for TD-PRICES); empty for the latest the daily DAG doesn't cover"),
    },
    tags=["mkt-data", "treasury", "securities", "backfill"],
    doc_md=__doc__,
)
def treasury_securities_backfill():
    @task
    def plan() -> list[dict]:
        p = get_current_context()["params"]
        print(f"params: source={p.get('source')!r} start={p.get('start')!r} end={p.get('end')!r}")
        batches = plan_batches(p.get("source") or "all", p.get("start"), p.get("end"), datetime.now(UTC))
        for b in batches:
            print(f"plan: {b['source']} {b['year']}: {len(b['periods'])} periods, {b['periods'][0]} to "
                  f"{b['periods'][-1]}" + (f" ({b['calendar']})" if "calendar" in b else ""))
        print(f"plan: {len(batches)} source-years, {sum(len(b['periods']) for b in batches)} periods")
        return batches

    # Each finished year marks both Assets, so the loads keep up a year at a time.
    @task(max_active_tis_per_dagrun=1, outlets=[TREASURY_SECURITIES, TREASURY_PRICES],
          execution_timeout=timedelta(hours=1))
    def capture_year(batch: dict) -> dict:
        out = capture_batch(batch)
        print({k: v for k, v in out.items() if k != "failed"})
        for f in out["failed"]:
            print("failed:", f)
        return out

    @task(trigger_rule="all_done")
    def report(results: list[dict]) -> dict:
        results = [r for r in results if r]
        failed = [f | {"source": r["source"]} for r in results for f in r["failed"]]
        by_source: dict[str, dict] = {}
        for r in results:
            s = by_source.setdefault(r["source"], {"years": 0, "periods": 0, "new": 0, "unchanged": 0, "empty": 0})
            for k in ("periods", "new", "unchanged", "empty"):
                s[k] += r[k]
            s["years"] += 1
        summary = {"sources": by_source, "failed": failed}
        print(summary)
        if failed:
            raise RuntimeError(f"{len(failed)} period(s) failed; re-run to retry them: {failed[:10]}")
        return summary

    report(capture_year.expand(batch=plan()))


treasury_securities_backfill()
