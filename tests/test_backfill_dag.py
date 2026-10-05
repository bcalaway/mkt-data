"""The backfill DAG's month planning (dags/treasury_cmt_backfill.py), with Airflow stubbed out."""

import importlib.util
import sys
import types
from datetime import UTC, datetime
from pathlib import Path

import pytest

DAG = Path(__file__).resolve().parent.parent / "dags" / "treasury_cmt_backfill.py"


@pytest.fixture
def backfill(monkeypatch):
    sdk = types.ModuleType("airflow.sdk")

    class _Task:  # stands in for a TaskFlow task: calling or mapping it only records the wiring
        def __init__(self, fn):
            self.fn = fn

        def __call__(self, *a, **k):
            return self

        def expand(self, **k):
            return self

    def task(*a, **k):
        return _Task(a[0]) if a and callable(a[0]) else _Task

    sdk.task = task
    sdk.dag = lambda *a, **k: (lambda f: f)
    sdk.Asset = sdk.Param = lambda *a, **k: (a, k)
    sdk.get_current_context = dict
    jobs = types.ModuleType("home_platform_jobs")
    jobs.AppJobError = RuntimeError
    jobs.call_app_job = None
    monkeypatch.setitem(sys.modules, "airflow", types.ModuleType("airflow"))
    monkeypatch.setitem(sys.modules, "airflow.sdk", sdk)
    monkeypatch.setitem(sys.modules, "home_platform_jobs", jobs)
    spec = importlib.util.spec_from_file_location("backfill_dag", DAG)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)  # defines the DAG with the stubs
    return mod


NOW = datetime(2026, 10, 5, tzinfo=UTC)


def test_months(backfill):
    assert backfill.months("2025-11", "2026-02") == ["2025-11", "2025-12", "2026-01", "2026-02"]
    assert backfill.last_month(NOW) == "2026-09"
    assert backfill.last_month(datetime(2026, 1, 15, tzinfo=UTC)) == "2025-12"


def test_full_history_plan(backfill):
    batches = backfill.plan_batches("both", "", "", NOW)
    ust = [b for b in batches if b["source"] == "UST-PAR"]
    h15 = [b for b in batches if b["source"] == "H15-TCM"]
    assert ust[0]["periods"][0] == "1990-01" and ust[-1]["periods"][-1] == "2026-09"
    assert h15[0]["periods"][0] == "1962-01" and len(h15) == 2026 - 1962 + 1
    assert sum(len(b["periods"]) for b in ust) == 36 * 12 + 9
    assert all(len(b["periods"]) == 12 for b in ust[:-1])


def test_a_narrowed_plan_never_starts_before_the_source(backfill):
    batches = backfill.plan_batches("UST-PAR", "1985-01", "1990-03", NOW)
    assert [b["periods"] for b in batches] == [["1990-01", "1990-02", "1990-03"]]


@pytest.mark.parametrize("given,month", [
    ("1990-01", "1990-01"), ("1990-1", "1990-01"), (" 1990-12 ", "1990-12"), ("1990-12-31", "1990-12"),
    ("1990/03", "1990-03"), ("", ""), (None, ""),
])
def test_month_params(backfill, given, month):
    assert backfill.month_param(given, "start") == month


@pytest.mark.parametrize("bad", ["Jan 1990", "1990-13", "90-01"])
def test_bad_month_params(backfill, bad):
    with pytest.raises(ValueError, match="isn't a month"):
        backfill.month_param(bad, "start")


def test_an_empty_plan_is_an_error_not_a_quiet_success(backfill):
    with pytest.raises(ValueError, match="nothing to capture"):
        backfill.plan_batches("UST-PAR", "1990-12", "1990-01", NOW)
    with pytest.raises(ValueError, match="source"):
        backfill.plan_batches("UST", "", "", NOW)
    assert len(backfill.plan_batches("UST-PAR", "1990-1", "1990-12-31", NOW)[0]["periods"]) == 12


def test_a_failed_fetch_is_retried_and_a_parse_failure_is_not(backfill):
    calls, pauses = [], []

    def flaky(app, job, timeout):
        calls.append(job)
        if len(calls) < 3:
            raise backfill.AppJobError("mkt-data POST ...: HTTP 502: fetch failed: empty response")
        return {"new_capture": True}

    assert backfill.capture_with_retries("H15-TCM", "1980-03", call=flaky, sleep=pauses.append) == {"new_capture": True}
    assert len(calls) == 3 and pauses == [10, 30]

    def broken(app, job, timeout):
        calls.append(job)
        raise backfill.AppJobError("HTTP 422: parse failed")

    calls.clear()
    with pytest.raises(backfill.AppJobError, match="422"):
        backfill.capture_with_retries("UST-PAR", "2010-10", call=broken, sleep=pauses.append)
    assert len(calls) == 1

    def down(app, job, timeout):
        calls.append(job)
        raise backfill.AppJobError("HTTP 502: fetch failed")

    calls.clear()
    pauses.clear()
    with pytest.raises(backfill.AppJobError):
        backfill.capture_with_retries("H15-TCM", "1980-04", call=down, sleep=pauses.append)
    assert len(calls) == 4 and pauses == [10, 30, 60]
