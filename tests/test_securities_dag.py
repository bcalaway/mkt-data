"""The Treasury securities capture DAGs' logic (dags/treasury_securities_capture.py), with Airflow stubbed out."""

import importlib.util
import sys
import types
from datetime import date
from pathlib import Path

import pytest

DAG = Path(__file__).resolve().parent.parent / "dags" / "treasury_securities_capture.py"


class JobError(RuntimeError):
    pass


@pytest.fixture
def mod(monkeypatch):
    sdk = types.ModuleType("airflow.sdk")

    def task(*a, **k):
        def wrap(fn):
            return lambda *x, **y: None

        return wrap(a[0]) if a and callable(a[0]) else wrap

    sdk.task = task
    sdk.dag = lambda *a, **k: (lambda f: f)
    sdk.CronTriggerTimetable = sdk.Param = lambda *a, **k: (a, k)
    sdk.get_current_context = dict
    jobs = types.ModuleType("home_platform_jobs")
    jobs.AppJobError = JobError
    jobs.call_app_job = None
    monkeypatch.setitem(sys.modules, "airflow", types.ModuleType("airflow"))
    monkeypatch.setitem(sys.modules, "airflow.sdk", sdk)
    monkeypatch.setitem(sys.modules, "home_platform_jobs", jobs)
    spec = importlib.util.spec_from_file_location("securities_dags", DAG)
    m = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(m)
    return m


def test_months(mod):
    assert mod.months(date(2026, 10, 20), ahead=1) == ["2026-10", "2026-11"]
    assert mod.months(date(2026, 12, 3), ahead=1) == ["2026-11", "2026-12", "2027-01"]
    assert mod.previous_months(date(2026, 1, 15)) == ["2025-12", "2026-01"]
    assert mod.years(date(2026, 1, 9)) == ["2025", "2026"] and mod.years(date(2026, 2, 1)) == ["2026"]


def _calendar(closed: set[date], fail=False):
    def call(app, path, params=None, method="POST", **kw):
        if fail:
            raise JobError("calendar-svc down")
        return {"business_day": date.fromisoformat(params["on"]) not in closed}

    return call


def test_price_days(mod):
    # Tuesday after Columbus Day: the previous business day is Friday.
    assert mod.price_days(date(2026, 10, 13), _calendar({date(2026, 10, 12)})) == ["2026-10-09", "2026-10-13"]
    assert mod.price_days(date(2026, 10, 12), _calendar({date(2026, 10, 12)})) == []
    assert mod.price_days(date(2026, 10, 10), _calendar(set())) == []  # Saturday
    # calendar-svc down: weekdays stand in.
    assert mod.price_days(date(2026, 10, 13), _calendar(set(), fail=True)) == ["2026-10-12", "2026-10-13"]


def test_capture_retries_failed_fetches_only(mod):
    calls, pauses = [], []

    def call(app, path, **kw):
        calls.append(path)
        if len(calls) < 3:
            raise JobError("HTTP 502: fetch failed")
        return {"period": "2026-10"}

    assert mod.capture("TD-SECURITIES", "2026-10", call, pauses.append) == {"period": "2026-10"}
    assert calls == ["securities/TD-SECURITIES/capture?period=2026-10"] * 3 and pauses == [10, 30]

    def bad(app, path, **kw):
        raise JobError("HTTP 400: bad period")

    with pytest.raises(JobError):
        mod.capture("TD-SECURITIES", "x", bad, pauses.append)


def test_capture_all_tries_every_period_then_fails(mod):
    def call(app, path, **kw):
        if path.endswith("2026-10"):
            raise JobError("HTTP 400")
        return {"period": path[-7:]}

    with pytest.raises(RuntimeError, match=r"1 of 2 periods failed: \['2026-10'\]"):
        mod.capture_all("FD-AUCTIONS", ["2026-09", "2026-10"], call, lambda s: None)


def test_periods_for_each_source(mod):
    today = date(2026, 10, 6)
    assert mod.periods_for("TD-SECURITIES", today) == ["2026-10", "2026-11"]
    assert mod.periods_for("FD-AUCTIONS", date(2026, 10, 2)) == ["2026-09", "2026-10", "2026-11"]
    assert mod.periods_for("FD-MSPD-STRIPS", today) == ["2026-09", "2026-10"]
    assert mod.periods_for("BLS-CPI", today) == ["2026"]
    assert mod.periods_for("TD-PRICES", today, _calendar(set())) == ["2026-10-05", "2026-10-06"]
    assert set(mod.SOURCES) == {"TD-SECURITIES", "TD-PRICES", "FD-AUCTIONS", "FD-MSPD-STRIPS", "BLS-CPI"}


def test_parse_periods(mod):
    assert mod.parse_periods("1979-01, 1980-01 1979-01,,") == ["1979-01", "1980-01"]
    assert mod.parse_periods("") == []
