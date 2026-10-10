"""The swap-curve DAGs' logic (dags/swap_curves.py), with Airflow stubbed out."""

import importlib.util
import sys
import types
from datetime import date
from pathlib import Path

import pytest

DAG = Path(__file__).resolve().parent.parent / "dags" / "swap_curves.py"


class JobError(RuntimeError):
    pass


@pytest.fixture
def mod(monkeypatch):
    sdk = types.ModuleType("airflow.sdk")

    class _Ref:  # a task's output: only wired up (>>), never run
        def __rshift__(self, other):
            return other

        def __rrshift__(self, other):
            return self

    def task(*a, **k):
        def wrap(fn):
            return lambda *x, **y: _Ref()

        return wrap(a[0]) if a and callable(a[0]) else wrap

    sdk.task = task
    sdk.dag = lambda *a, **k: (lambda f: f)
    sdk.CronTriggerTimetable = sdk.Param = sdk.Asset = lambda *a, **k: (a, k)
    exc = types.ModuleType("airflow.sdk.exceptions")
    exc.AirflowSkipException = type("AirflowSkipException", (Exception,), {})
    sdk.get_current_context = dict
    jobs = types.ModuleType("home_platform_jobs")
    jobs.AppJobError = JobError
    jobs.call_app_job = None
    monkeypatch.setitem(sys.modules, "airflow", types.ModuleType("airflow"))
    monkeypatch.setitem(sys.modules, "airflow.sdk", sdk)
    monkeypatch.setitem(sys.modules, "airflow.sdk.exceptions", exc)
    monkeypatch.setitem(sys.modules, "home_platform_jobs", jobs)
    spec = importlib.util.spec_from_file_location("swap_curve_dags", DAG)
    m = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(m)
    return m


def test_recent_weekdays(mod):
    assert mod.recent_weekdays(date(2026, 10, 12)) == ["2026-10-06", "2026-10-07", "2026-10-08", "2026-10-09",
                                                       "2026-10-12"]
    assert mod.recent_weekdays(date(2026, 10, 11), 2) == ["2026-10-08", "2026-10-09"]  # a Sunday


def test_backfill_periods(mod):
    today = date(2026, 10, 12)
    assert mod.backfill_periods("USD", "2026-10-08", "", today) == ["2026-10-08", "2026-10-09"]  # to yesterday
    assert mod.backfill_periods("GBP", "", "2021-02-02", today) == ["2021-02-01", "2021-02-02"]
    assert mod.backfill_periods("USD", "2019-01-01", "2021-04-01", today) == ["2021-04-01"]  # not before FIRST


def test_first_dates_match_the_sources(mod):
    from app.swaps import sources as sw

    assert {c: sw.SOURCES[f"SPGMI-RFR-{c}"].first_period for c in mod.CURRENCIES} == mod.FIRST


def test_capture_all(mod):
    calls = []

    def call(app, path, timeout):
        calls.append(path)
        if path.endswith("2026-10-08"):
            raise JobError("HTTP 502: fetch failed: x: NOT_PUBLISHED: Interest Rates not available")
        return {"period": path[-10:], "added": 1}

    got = mod.capture_all("USD", ["2026-10-08", "2026-10-09"], call, lambda s: None)
    assert [r["period"] for r in got] == ["2026-10-09"] and mod.changed(got)
    assert calls[0] == "swaps/SPGMI-RFR-USD/capture?period=2026-10-08"

    def terms(app, path, timeout):
        raise JobError("HTTP 502: fetch failed: x: TERMS_NOT_ACCEPTED: Username not known")

    with pytest.raises(RuntimeError, match="terms"):
        mod.capture_all("USD", ["2026-10-08", "2026-10-09"], terms, lambda s: None)

    tries = []

    def flaky(app, path, timeout):
        tries.append(path)
        raise JobError("HTTP 502: fetch failed: timeout")

    with pytest.raises(RuntimeError, match="1 of 1 dates failed"):
        mod.capture_all("EUR", ["2026-10-09"], flaky, lambda s: None)
    assert len(tries) == 4  # three pauses, then given up
