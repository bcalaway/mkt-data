"""mkt-data: the daily Treasury securities captures (docs/phase-3.md, step 1).

Raw capture only: there are no parsers yet, so nothing is marked for other
services. The point is to start the raw history now and read the real bytes
on the hub before writing parsers.

One DAG, weekdays at 7:15 p.m. New York time, one task per source so a
failing source doesn't hold up the others:

- TD-SECURITIES and FD-AUCTIONS: the current and next month of auctions
  (announcements land up to a week or so ahead; results on auction day),
  plus the previous month in a month's first five days.
- TD-PRICES: today's FedInvest prices and the previous SIFMA-US business
  day's (in case today's weren't up yet, or yesterday's changed), only on a
  SIFMA-US business day.
- FD-MSPD-STRIPS: the previous and current month (the statement for a month
  comes out a few business days into the next).
- BLS-CPI: the current year, plus the previous one in January.

Once TD-SECURITIES and FD-AUCTIONS are captured, `compare_auctions` cross-checks
TreasuryDirect's auction records against Fiscal Data's (the metrics carry
the result). After TD-PRICES, a mark task sets the Asset `mkt_data_treasury_prices` when
any of its days gained, changed or lost a price, so quote-svc's load runs.
After TD-SECURITIES, a mark task sets the Asset `mkt_data_treasury_securities`
when any of its months gained, changed or lost an auction, so secmaster-svc's
load (scheduled on it) runs when there's something new.

A second, manual DAG, `mkt_data__treasury_securities_probe`, captures the
periods given in its form for one source, for fixtures and spot checks. Run
with the form left as it is (source "all", no periods), it samples one
period a year from each source's earliest plausible year to now (not
BLS-CPI: its history is known, 1913 on, and its keyless API allows 25
requests a day), and logs each period's size, so a source's first year shows
where the answers stop being empty. Before the real backfill (step 5).

A failed fetch (HTTP 502 from the job) is tried again after 10, 30 and 60
seconds within the task, then the task retries once an hour later. The work
runs in the mkt-data container; this DAG only calls its job API (ADR-0031 in
nyc_pa_aws_gitops). New DAGs start paused.
"""

import sys
import time
from datetime import UTC, date, datetime, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo

from airflow.sdk import Asset, CronTriggerTimetable, Param, dag, get_current_context, task

try:
    from airflow.sdk.exceptions import AirflowSkipException
except ImportError:  # older Task SDKs
    from airflow.exceptions import AirflowSkipException

# The platform's helper lives at Airflow's DAG root (see treasury_cmt_daily.py).
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from home_platform_jobs import AppJobError, call_app_job

NEW_YORK = ZoneInfo("America/New_York")
# secmaster-svc's load (secmaster_svc__load) is scheduled on this: marked when
# TreasuryDirect's records (TD-SECURITIES) gain, change or lose an auction.
TREASURY_SECURITIES = Asset("mkt_data_treasury_securities")
# quote-svc's load is scheduled on this: marked when FedInvest's prices for a day were added, changed or removed.
TREASURY_PRICES = Asset("mkt_data_treasury_prices")
FETCH_PAUSES = (10, 30, 60)
LOOKBACK_DAYS = 10


def months(today: date, ahead: int = 0) -> list[str]:
    """The current month, `ahead` months after it, and the previous one in a month's first five days."""
    out = []
    if today.day <= 5:
        out.append(f"{today.replace(day=1) - timedelta(days=1):%Y-%m}")
    first = today.replace(day=1)
    for n in range(ahead + 1):
        k = first.year * 12 + first.month - 1 + n
        out.append(f"{k // 12:04d}-{k % 12 + 1:02d}")
    return out


def previous_months(today: date) -> list[str]:
    """The previous month and the current one."""
    return [f"{today.replace(day=1) - timedelta(days=1):%Y-%m}", f"{today:%Y-%m}"]


def years(today: date) -> list[str]:
    return ([str(today.year - 1)] if today.month == 1 else []) + [str(today.year)]


def business_day(calendar: str, day: date, call=None) -> bool | None:
    """calendar-svc's answer for one day: True, False, or None if it couldn't answer."""
    call = call or call_app_job
    try:
        r = call("calendar-svc", f"calendars/{calendar}/business-day", {"on": day.isoformat()}, method="GET")
    except AppJobError as e:
        print(f"calendar-svc couldn't say whether {day} is a {calendar} business day: {e}")
        return None
    return bool(r["business_day"])


def price_days(today: date, call=None) -> list[str]:
    """The previous SIFMA-US business day and today, or nothing if today isn't one.

    If calendar-svc can't answer, weekdays stand in for business days: a
    capture on a holiday only stores whatever FedInvest answers for it.
    """
    if today.weekday() >= 5 or business_day("SIFMA-US", today, call) is False:
        return []
    prev = None
    for n in range(1, LOOKBACK_DAYS + 1):
        day = today - timedelta(days=n)
        if day.weekday() >= 5:
            continue
        answer = business_day("SIFMA-US", day, call)
        if answer is None or answer:
            prev = day
            break
    return [d.isoformat() for d in (prev, today) if d]


def capture(source: str, period: str, call=None, sleep=time.sleep) -> dict:
    """One capture job call, retried on HTTP 502 (a failed fetch); other errors raise at once."""
    call = call or call_app_job
    for pause in (*FETCH_PAUSES, None):
        try:
            return call("mkt-data", f"securities/{source}/capture?period={period}", timeout=180)
        except AppJobError as e:
            if pause is None or "HTTP 502" not in str(e):
                raise
            print(f"{source} {period}: fetch failed, trying again in {pause} s: {str(e)[:200]}")
            sleep(pause)
    raise AssertionError("unreachable")


def capture_all(source: str, periods: list[str], call=None, sleep=time.sleep) -> list[dict]:
    """Capture every period; report each, then fail if any failed (after trying them all)."""
    results, failed = [], []
    for p in periods:
        try:
            r = capture(source, p, call, sleep)
        except AppJobError as e:
            print(f"{source} {p}: failed: {str(e)[:300]}")
            failed.append(p)
            continue
        print({k: r.get(k) for k in ("period", "capture_id", "new_capture", "size_bytes", "content_type")})
        results.append(r)
    if failed:
        raise RuntimeError(f"{source}: {len(failed)} of {len(periods)} periods failed: {failed}")
    return results


def changed(results: list[dict]) -> bool:
    return any(r.get("added") or r.get("changed") or r.get("removed") for r in results)


def periods_for(source: str, today: date, call=None) -> list[str]:
    if source in ("TD-SECURITIES", "FD-AUCTIONS"):
        return months(today, ahead=1)
    if source == "TD-PRICES":
        return price_days(today, call)
    if source == "FD-MSPD-STRIPS":
        return previous_months(today)
    if source == "BLS-CPI":
        return years(today)
    raise ValueError(f"unknown source {source}")


SOURCES = ("TD-SECURITIES", "TD-PRICES", "FD-AUCTIONS", "FD-MSPD-STRIPS", "BLS-CPI")


@dag(
    dag_id="mkt_data__treasury_securities_capture",
    schedule=CronTriggerTimetable("15 19 * * 1-5", timezone="America/New_York"),
    start_date=datetime(2026, 10, 1, tzinfo=UTC),
    catchup=False,
    max_active_runs=1,
    dagrun_timeout=timedelta(hours=4),
    tags=["mkt-data", "treasury", "securities"],
    doc_md=__doc__,
)
def treasury_securities_capture():
    captured = {}
    for source in SOURCES:

        @task(task_id=f"capture_{source.lower().replace('-', '_')}", retries=1, retry_delay=timedelta(hours=1))
        def run(source: str = source) -> list[dict]:
            today = datetime.now(NEW_YORK).date()
            periods = periods_for(source, today)
            if not periods:
                print(f"{source}: nothing to capture today")
                return []
            return capture_all(source, periods)

        got = run()
        captured[source] = got
        if source == "TD-SECURITIES":

            @task(outlets=[TREASURY_SECURITIES])
            def mark_treasury_securities(results: list[dict]) -> str:
                if not changed(results):
                    raise AirflowSkipException("no auction added, changed or removed: secmaster-svc has nothing to load")
                return "marked"

            mark_treasury_securities(got)
        elif source == "TD-PRICES":

            @task(outlets=[TREASURY_PRICES])
            def mark_treasury_prices(results: list[dict]) -> str:
                if not changed(results):
                    raise AirflowSkipException("no price added, changed or removed: quote-svc has nothing to load")
                return "marked"

            mark_treasury_prices(got)

    # TreasuryDirect's auctions against Fiscal Data's, once both are in (whatever happened to either).
    @task(trigger_rule="all_done", retries=1, retry_delay=timedelta(minutes=10))
    def compare_auctions() -> dict:
        result = call_app_job("mkt-data", "securities/compare", timeout=600)
        print({k: v for k, v in result.items() if k != "fields_differing"})
        for f in result.get("fields_differing", []):
            print(f"differs: {f['field']}: {f['different']} records, e.g. {f['examples'][:2]}")
        return result

    [captured["TD-SECURITIES"], captured["FD-AUCTIONS"]] >> compare_auctions()


treasury_securities_capture()


# Sample periods per source for the probe's default run: one a year, on a day
# or month that always has data once the source does.
SAMPLE_FROM = {"TD-SECURITIES": 1979, "FD-AUCTIONS": 1979, "FD-MSPD-STRIPS": 1985, "TD-PRICES": 2000}


def sample_periods(source: str, today: date) -> list[str]:
    """One period a year: February's auctions (a refunding month), January's MSPD, and the
    second Wednesday of January's prices (never a holiday)."""
    out = []
    for year in range(SAMPLE_FROM[source], today.year + 1):
        if source == "TD-PRICES":
            jan1 = date(year, 1, 1)
            day = jan1 + timedelta(days=(2 - jan1.weekday()) % 7 + 7)
            if day <= today:
                out.append(day.isoformat())
        elif source == "FD-MSPD-STRIPS":
            out.append(f"{year}-01")
        elif date(year, 2, 1) <= today:
            out.append(f"{year}-02")
    return out


def parse_periods(text: str) -> list[str]:
    """Periods from the probe form: comma- or space-separated, in the order given, duplicates dropped."""
    out = []
    for p in text.replace(",", " ").split():
        if p not in out:
            out.append(p)
    return out


@dag(
    dag_id="mkt_data__treasury_securities_probe",
    schedule=None,
    start_date=datetime(2026, 10, 1, tzinfo=UTC),
    catchup=False,
    max_active_runs=1,
    tags=["mkt-data", "treasury", "securities"],
    doc_md=__doc__,
    params={
        "source": Param("all", enum=["all", *SOURCES]),
        "periods": Param("", type="string",
                         description="Comma-separated: YYYY-MM (TD-SECURITIES, FD-AUCTIONS, FD-MSPD-STRIPS), "
                                     "YYYY-MM-DD (TD-PRICES) or YYYY (BLS-CPI). Empty: one sample period a year"),
    },
)
def treasury_securities_probe():
    @task
    def probe() -> dict:
        p = get_current_context()["params"]
        periods = parse_periods(p.get("periods") or "")
        source = p.get("source") or "all"
        if periods:
            if source == "all":
                raise ValueError("periods need a single source")
            return {source: capture_all(source, periods)}
        today = datetime.now(NEW_YORK).date()
        names = list(SAMPLE_FROM) if source == "all" else [source]
        report, failed = {}, []
        for name in names:
            try:
                report[name] = capture_all(name, sample_periods(name, today))
            except RuntimeError as e:  # some periods failed: logged above; carry on with the next source
                failed.append(str(e))
        if failed:
            raise RuntimeError("; ".join(failed))
        return report

    probe()


treasury_securities_probe()
