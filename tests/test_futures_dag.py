"""Phase 4's capture DAGs' logic (dags/futures_sources_capture.py), with Airflow stubbed out."""

import importlib.util
import sys
import types
from datetime import date
from pathlib import Path

import pytest

DAG = Path(__file__).resolve().parent.parent / "dags" / "futures_sources_capture.py"


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
    spec = importlib.util.spec_from_file_location("futures_dags", DAG)
    m = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(m)
    return m


def test_recent_months(mod):
    assert mod.recent_months(date(2026, 10, 20)) == ["2026-10"]
    assert mod.recent_months(date(2026, 10, 7)) == ["2026-09", "2026-10"]
    assert mod.recent_months(date(2026, 10, 1)) == ["2026-09"]  # October's first day isn't published yet
    assert mod.recent_months(date(2027, 1, 3)) == ["2026-12", "2027-01"]


def test_cftc_report_dates(mod):
    # Wednesday 2026-10-07: the latest report due was Friday 2026-10-02's (as of Tuesday 2026-09-29).
    assert mod.cftc_report_dates(date(2026, 10, 7)) == ["2026-09-22", "2026-09-29"]
    assert mod.cftc_report_dates(date(2026, 10, 9)) == ["2026-09-29", "2026-10-06"]  # Friday: today's is due
    assert mod.cftc_report_dates(date(2026, 10, 12)) == ["2026-09-29", "2026-10-06"]  # Monday after a holiday Friday


def test_periods_for_every_source(mod):
    for source in mod.SOURCES:
        assert mod.periods_for(source, date(2026, 10, 7))
    with pytest.raises(ValueError):
        mod.periods_for("NOPE", date(2026, 10, 7))


def _job(answers: dict):
    calls = []

    def call(app, path, **kw):
        calls.append(path)
        a = answers[path.split("?period=")[1]]
        if isinstance(a, Exception):
            raise a
        return a

    return call, calls


def test_nothing_published_is_logged_not_failed(mod):
    call, calls = _job({"2026-09": {"period": "2026-09"}, "2026-10": JobError("HTTP 502: fetch failed: NOT_PUBLISHED")})
    assert mod.capture_all("NYFED-SOFR", ["2026-09", "2026-10"], call, sleep=lambda s: None) == [{"period": "2026-09"}]
    assert calls == ["futures/NYFED-SOFR/capture?period=2026-09", "futures/NYFED-SOFR/capture?period=2026-10"]


def test_a_failed_fetch_is_retried_then_fails(mod):
    call, calls = _job({"2026-10": JobError("HTTP 502: fetch failed: timeout")})
    with pytest.raises(RuntimeError, match="1 of 1 periods failed"):
        mod.capture_all("ECB-EXR", ["2026-10"], call, sleep=lambda s: None)
    assert len(calls) == 4


def test_sample_periods(mod):
    tff = mod.sample_periods("CFTC-TFF", date(2026, 10, 7))
    assert tff[0] == "2006-06-20" and tff[-1] == "2026-06-16" and len(tff) == 21
    assert mod.sample_periods("NYFED-SOFR", date(2026, 10, 7)) == [f"{y}-06" for y in range(2018, 2027)]
