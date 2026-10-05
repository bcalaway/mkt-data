"""The daily Treasury CMT DAGs' logic (dags/treasury_cmt_daily.py), with Airflow stubbed out."""

import importlib.util
import sys
import types
from datetime import date
from pathlib import Path

import pytest

DAG = Path(__file__).resolve().parent.parent / "dags" / "treasury_cmt_daily.py"


class JobError(RuntimeError):
    pass


@pytest.fixture
def daily(monkeypatch):
    sdk = types.ModuleType("airflow.sdk")

    class _Task:  # stands in for a TaskFlow task: calling or chaining it only records the wiring
        def __init__(self, fn=None):
            self.fn = fn

        def __call__(self, *a, **k):
            return self

        def __rshift__(self, other):
            return other

    def task(*a, **k):
        return _Task(a[0]) if a and callable(a[0]) else _Task

    task.short_circuit = _Task
    sdk.task = task
    sdk.dag = lambda *a, **k: (lambda f: f)
    sdk.Asset = sdk.CronTriggerTimetable = lambda *a, **k: (a, k)
    exc = types.ModuleType("airflow.sdk.exceptions")
    exc.AirflowSkipException = type("AirflowSkipException", (Exception,), {})
    jobs = types.ModuleType("home_platform_jobs")
    jobs.AppJobError = JobError
    jobs.call_app_job = None
    monkeypatch.setitem(sys.modules, "airflow", types.ModuleType("airflow"))
    monkeypatch.setitem(sys.modules, "airflow.sdk", sdk)
    monkeypatch.setitem(sys.modules, "airflow.sdk.exceptions", exc)
    monkeypatch.setitem(sys.modules, "home_platform_jobs", jobs)
    spec = importlib.util.spec_from_file_location("daily_dags", DAG)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)  # defines both DAGs with the stubs
    return mod


def _calendar(closed: set[str], down: bool = False):
    calls = []

    def call(app, job, params, method):
        calls.append((app, job, params["on"], method))
        if down:
            raise JobError("calendar-svc unreachable")
        return {"business_day": params["on"] not in closed, "status": "closed" if params["on"] in closed else "open"}

    call.calls = calls
    return call


def test_periods(daily):
    assert daily.periods(date(2026, 10, 14)) == ["2026-10"]
    assert daily.periods(date(2026, 10, 5)) == ["2026-09", "2026-10"]
    assert daily.periods(date(2026, 1, 2)) == ["2025-12", "2026-01"]


def test_business_day_asks_calendar_svc(daily):
    call = _calendar({"2026-10-12"})
    assert daily.business_day("SIFMA-US", date(2026, 10, 12), call) is False
    assert daily.business_day("SIFMA-US", date(2026, 10, 13), call) is True
    assert call.calls[0] == ("calendar-svc", "calendars/SIFMA-US/business-day", "2026-10-12", "GET")


def test_an_unreachable_calendar_lets_the_run_go_ahead(daily):
    assert daily.business_day("FED", date(2026, 10, 12), _calendar(set(), down=True)) is None


def test_h15s_expected_day_skips_weekends_and_closes(daily):
    # Tuesday after Columbus Day: H.15 carries Friday's yields.
    call = _calendar({"2026-10-12"})
    assert daily.previous_business_day("SIFMA-US", date(2026, 10, 13), call) == date(2026, 10, 9)
    assert [c[2] for c in call.calls] == ["2026-10-12", "2026-10-09"]  # no weekend calls
    # Calendar-svc down: the previous weekday.
    down = _calendar(set(), down=True)
    assert daily.previous_business_day("SIFMA-US", date(2026, 10, 13), down) == date(2026, 10, 12)
    assert daily.previous_business_day("SIFMA-US", date(2026, 10, 12), down) == date(2026, 10, 9)


def test_landed_and_changed(daily):
    first_of_month = [{"period": "2026-09", "last_date": "2026-09-30", "added": 0},
                      {"period": "2026-10", "last_date": None, "added": 0}]
    assert not daily.landed(first_of_month, date(2026, 10, 1))
    assert daily.landed(first_of_month, date(2026, 9, 30))
    assert not daily.changed(first_of_month)
    assert daily.changed([{"added": 0, "changed": 1, "removed": 0}])
    assert daily.landed([{"last_date": "2026-10-02", "added": 14}], date(2026, 10, 2))


def test_a_failed_fetch_is_retried_within_the_task(daily):
    answers = [JobError("HTTP 502: empty response"), JobError("HTTP 502: empty response"), {"last_date": "2026-10-02"}]
    calls, slept = [], []

    def call(app, job, timeout):
        calls.append(job)
        a = answers.pop(0)
        if isinstance(a, Exception):
            raise a
        return a

    assert daily.capture_month("H15-TCM", "2026-10", call, slept.append) == {"last_date": "2026-10-02"}
    assert calls == ["rates/H15-TCM/capture?period=2026-10"] * 3 and slept == [10, 30]


def test_other_errors_and_a_last_failure_raise(daily):
    def parse_error(app, job, timeout):
        raise JobError("HTTP 422: parse failed")

    with pytest.raises(JobError, match="422"):
        daily.capture_month("UST-PAR", "2026-10", parse_error, lambda s: None)

    def always_502(app, job, timeout):
        raise JobError("HTTP 502: empty response")

    slept = []
    with pytest.raises(JobError, match="502"):
        daily.capture_month("H15-TCM", "2026-10", always_502, slept.append)
    assert slept == [10, 30, 60]
