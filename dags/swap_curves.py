"""mkt-data: the ISDA standard model's RFR swap curves from S&P Global Market Intelligence (docs/phase-4.md, "Swap
curves").

One file per currency (USD, EUR, GBP, JPY, CHF, AUD) every weekday, holidays included, due by 17:30 in the currency's
reference city (New York, Frankfurt, London, Tokyo, Zurich, Sydney). By 6:15 p.m. New York every one of the day's
files is out, so the daily DAG runs then, one task per currency so a failing one doesn't hold up the others. Each
task asks for the last few weekdays' files up to today: S&P can republish a day's curve after a correction (agreed
with ISDA), and a re-fetch whose XML is unchanged is just a check.

A date with nothing published (NOT_PUBLISHED from the job: not out yet) is logged, not a failure. S&P not knowing
the email or wanting its terms accepted again (TERMS_NOT_ACCEPTED, yearly) fails the task without retrying: Bill
re-accepts at https://rfr.spglobal.com. A failed fetch (HTTP 502) is tried again after 10, 30 and 60 seconds, then
the task retries once an hour later. A capture that added, changed or removed a par rate marks the Asset
`mkt_data_swap_curves`, for quote-svc.

A second, manual DAG, `mkt_data__swap_curves_backfill`, asks for every weekday in a range (default: each source's
first plausible date to yesterday) for one currency or all, a second apart, oldest first. Its log shows where each
source's history starts. The work runs in the mkt-data container; these DAGs only call its job API (ADR-0031 in
nyc_pa_aws_gitops). New DAGs start paused.
"""

import sys
import time
from datetime import UTC, date, datetime, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo

try:  # Airflow 3's home for it; 2.x's as a fallback (see treasury_cmt_daily.py)
    from airflow.sdk.exceptions import AirflowSkipException
except ImportError:
    from airflow.exceptions import AirflowSkipException
from airflow.sdk import Asset, CronTriggerTimetable, Param, dag, get_current_context, task

# The platform's helper lives at Airflow's DAG root (see treasury_cmt_daily.py).
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from home_platform_jobs import AppJobError, call_app_job

SWAP_CURVES = Asset("mkt_data_swap_curves")
NEW_YORK = ZoneInfo("America/New_York")
FETCH_PAUSES = (10, 30, 60)
WEEKDAYS_BACK = 5  # today and the four weekdays before it, re-fetched each evening
BACKFILL_PAUSE_SECONDS = 1
# What mkt-data says (app/swaps/sources.py): nothing for that date yet; the email's terms need accepting.
NOT_PUBLISHED = "NOT_PUBLISHED"
TERMS = "TERMS_NOT_ACCEPTED"

CURRENCIES = ("USD", "EUR", "GBP", "JPY", "CHF", "AUD")
# The earliest date each source's job accepts (first_period in app/swaps/sources.py).
FIRST = {"USD": "2021-04-01", "EUR": "2021-04-01", "GBP": "2021-02-01", "JPY": "2021-04-01", "CHF": "2021-04-01",
         "AUD": "2021-04-01"}


def source(ccy: str) -> str:
    return f"SPGMI-RFR-{ccy}"


def recent_weekdays(today: date, n: int = WEEKDAYS_BACK) -> list[str]:
    """The `n` latest weekdays up to and including today, oldest first."""
    out, d = [], today
    while len(out) < n:
        if d.weekday() < 5:
            out.append(d.isoformat())
        d -= timedelta(days=1)
    return list(reversed(out))


def weekdays_between(first: date, last: date) -> list[str]:
    out, d = [], first
    while d <= last:
        if d.weekday() < 5:
            out.append(d.isoformat())
        d += timedelta(days=1)
    return out


def changed(results: list[dict]) -> bool:
    return any(r.get("added") or r.get("changed") or r.get("removed") for r in results)


def capture(ccy: str, period: str, call=None, sleep=time.sleep) -> dict:
    """One capture job call, retried on HTTP 502 (a failed fetch); other errors, NOT_PUBLISHED and TERMS raise at
    once."""
    call = call or call_app_job
    for pause in (*FETCH_PAUSES, None):
        try:
            return call("mkt-data", f"swaps/{source(ccy)}/capture?period={period}", timeout=180)
        except AppJobError as e:
            msg = str(e)
            if pause is None or "HTTP 502" not in msg or NOT_PUBLISHED in msg or TERMS in msg:
                raise
            print(f"{ccy} {period}: fetch failed, trying again in {pause} s: {msg[:200]}")
            sleep(pause)
    raise AssertionError("unreachable")


def capture_all(ccy: str, periods: list[str], call=None, sleep=time.sleep, pause: float = 0) -> list[dict]:
    """Capture every date; report each, then fail if any failed (after trying them all). TERMS stops at once: every
    later date would fail the same way."""
    results, failed, missing = [], [], []
    for p in periods:
        try:
            r = capture(ccy, p, call, sleep)
        except AppJobError as e:
            if NOT_PUBLISHED in str(e):
                missing.append(p)
                continue
            if TERMS in str(e):
                raise RuntimeError(f"{ccy}: S&P wants its terms accepted: {str(e)[:300]}") from None
            print(f"{ccy} {p}: failed: {str(e)[:300]}")
            failed.append(p)
            continue
        finally:
            if pause:
                sleep(pause)
        print({k: r.get(k) for k in ("period", "capture_id", "new_capture", "values", "added", "changed")})
        results.append(r)
    if missing:
        print(f"{ccy}: nothing published for {len(missing)} date(s), {missing[0]} to {missing[-1]}")
    if failed:
        raise RuntimeError(f"{ccy}: {len(failed)} of {len(periods)} dates failed: {failed}")
    return results


@dag(
    dag_id="mkt_data__swap_curves_capture",
    schedule=CronTriggerTimetable("15 18 * * 1-5", timezone="America/New_York"),
    start_date=datetime(2026, 10, 1, tzinfo=UTC),
    catchup=False,
    max_active_runs=1,
    dagrun_timeout=timedelta(hours=3),
    tags=["mkt-data", "swaps", "isda"],
    doc_md=__doc__,
)
def swap_curves_capture():
    for ccy in CURRENCIES:

        @task(task_id=f"capture_{ccy.lower()}", retries=1, retry_delay=timedelta(hours=1))
        def run(ccy: str = ccy) -> list[dict]:
            return capture_all(ccy, recent_weekdays(datetime.now(NEW_YORK).date()))

        @task(task_id=f"mark_{ccy.lower()}", outlets=[SWAP_CURVES])
        def mark(results: list[dict], ccy: str = ccy) -> str:
            if not changed(results):
                raise AirflowSkipException(f"{ccy}: nothing new for quote-svc")
            return "marked"

        mark(run())


swap_curves_capture()


def backfill_periods(ccy: str, start: str, end: str, today: date) -> list[str]:
    first = date.fromisoformat(start) if start else date.fromisoformat(FIRST[ccy])
    first = max(first, date.fromisoformat(FIRST[ccy]))
    last = date.fromisoformat(end) if end else today - timedelta(days=1)
    return weekdays_between(first, min(last, today))


@dag(
    dag_id="mkt_data__swap_curves_backfill",
    schedule=None,
    start_date=datetime(2026, 10, 1, tzinfo=UTC),
    catchup=False,
    max_active_runs=1,
    tags=["mkt-data", "swaps", "isda"],
    doc_md=__doc__,
    params={
        "currency": Param("all", enum=["all", *CURRENCIES]),
        "start": Param("", type="string", description="YYYY-MM-DD; empty: the source's first plausible date"),
        "end": Param("", type="string", description="YYYY-MM-DD; empty: yesterday"),
    },
)
def swap_curves_backfill():
    @task(outlets=[SWAP_CURVES])
    def backfill() -> dict:
        p = get_current_context()["params"]
        today = datetime.now(NEW_YORK).date()
        chosen = CURRENCIES if (p.get("currency") or "all") == "all" else (p["currency"],)
        report, failed = {}, []
        for ccy in chosen:
            periods = backfill_periods(ccy, p.get("start") or "", p.get("end") or "", today)
            try:
                got = capture_all(ccy, periods, pause=BACKFILL_PAUSE_SECONDS)
            except RuntimeError as e:  # logged above; carry on with the next currency
                failed.append(str(e))
                continue
            report[ccy] = {"dates": len(periods), "captured": len(got),
                           "first": got[0]["period"] if got else None, "last": got[-1]["period"] if got else None}
            print(ccy, report[ccy])
        if failed:
            raise RuntimeError("; ".join(failed))
        return report

    backfill()


swap_curves_backfill()
