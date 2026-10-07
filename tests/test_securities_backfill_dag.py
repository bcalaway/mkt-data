"""The securities backfill DAG's planning and capture loop (dags/treasury_securities_backfill.py), with Airflow stubbed out."""

import importlib.util
import sys
import types
from datetime import UTC, date, datetime
from pathlib import Path

import pytest

DAG = Path(__file__).resolve().parent.parent / "dags" / "treasury_securities_backfill.py"
NOW = datetime(2026, 10, 7, 12, tzinfo=UTC)
# SIFMA-US's 2025 closes (as calendar-svc lists them), and an early close that isn't one.
CLOSES_2025 = {date(2025, d[0], d[1]) for d in [(1, 1), (1, 9), (1, 20), (2, 17), (4, 18), (5, 26), (6, 19), (7, 4),
                                                  (9, 1), (10, 13), (11, 11), (11, 27), (12, 25)]}


class JobError(RuntimeError):
    pass


@pytest.fixture
def mod(monkeypatch):
    sdk = types.ModuleType("airflow.sdk")

    class _Task:
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
    jobs.AppJobError = JobError
    jobs.call_app_job = None
    monkeypatch.setitem(sys.modules, "airflow", types.ModuleType("airflow"))
    monkeypatch.setitem(sys.modules, "airflow.sdk", sdk)
    monkeypatch.setitem(sys.modules, "home_platform_jobs", jobs)
    spec = importlib.util.spec_from_file_location("securities_backfill_dag", DAG)
    m = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(m)
    return m


def _closes(year):
    return {d for d in CLOSES_2025 if d.year == year}


def test_full_history_plan(mod):
    batches = mod.plan_batches("all", None, None, NOW, closes=_closes)
    by = {}
    for b in batches:
        by.setdefault(b["source"], []).append(b)
    assert list(by) == ["TD-SECURITIES", "FD-AUCTIONS", "FD-MSPD-STRIPS", "TD-PRICES"]  # securities before prices
    td = by["TD-SECURITIES"]
    assert td[0]["periods"][0] == "1980-01" and td[-1]["periods"][-1] == "2026-09"  # this month is the daily DAG's
    assert by["FD-MSPD-STRIPS"][0]["periods"][0] == "2001-01"
    prices = by["TD-PRICES"]
    assert prices[0]["periods"][0] == "2008-01-02" and prices[-1]["periods"][-1] == "2026-10-06"
    assert [b["year"] for b in prices] == [str(y) for y in range(2008, 2027)]


def test_price_days_skip_weekends_and_closes(mod):
    [b] = mod.plan_batches("TD-PRICES", "2025-01", "2025-12", NOW, closes=_closes)
    assert len(b["periods"]) == 261 - 13 and b["calendar"] == "SIFMA-US"
    assert "2025-09-01" not in b["periods"] and "2025-09-02" in b["periods"] and "2025-09-06" not in b["periods"]
    # calendar-svc down: weekdays stand in, and the batch says so.
    [b] = mod.plan_batches("TD-PRICES", "2025-09-01", "2025-09-05", NOW, closes=lambda y: None)
    assert b["periods"] == [f"2025-09-0{d}" for d in range(1, 6)] and b["calendar"] == "weekdays"


def test_a_narrowed_plan_stays_inside_the_source(mod):
    assert [b["periods"] for b in mod.plan_batches("FD-MSPD-STRIPS", "1999-11", "2001-02", NOW)] == [["2001-01", "2001-02"]]
    with pytest.raises(ValueError, match="nothing to capture"):
        mod.plan_batches("FD-AUCTIONS", "2026-10", None, NOW)  # this month is the daily DAG's
    with pytest.raises(ValueError, match="isn't one of"):
        mod.plan_batches("BLS-CPI", None, None, NOW)
    with pytest.raises(ValueError, match="isn't a month"):
        mod.plan_batches("TD-SECURITIES", "June 1990", None, NOW)


def test_closed_days_asks_calendar_svc_for_the_year(mod):
    asked = []

    def call(app, path, params=None, method="POST", **k):
        asked.append((app, path, params, method))
        return {"closes": [{"date": "2025-09-01", "status": "closed"}, {"date": "2025-11-28", "status": "early_close"}]}

    assert mod.closed_days(2025, call) == {date(2025, 9, 1)}
    assert asked == [("calendar-svc", "calendars/SIFMA-US/closes",
                      {"start": "2025-01-01", "end": "2025-12-31", "limit": "5000"}, "GET")]

    def down(*a, **k):
        raise JobError("HTTP 503")

    assert mod.closed_days(2025, down) is None


def test_capture_batch_counts_and_carries_on(mod):
    def call(app, path, timeout=None):
        period = path.rsplit("=", 1)[1]
        if period == "2008-01-03":
            raise JobError("HTTP 422: parse failed")
        if period == "2008-01-04":
            return {"new_capture": False, "values": 1200}
        if period == "2008-01-02":
            return {"new_capture": True, "values": 0}  # before FedInvest's first day: an empty page
        return {"new_capture": True, "values": 1300}

    slept = []
    out = mod.capture_batch({"source": "TD-PRICES", "year": "2008",
                             "periods": ["2008-01-02", "2008-01-03", "2008-01-04", "2008-01-07"]}, call, slept.append)
    assert (out["new"], out["unchanged"], out["empty"], out["values"]) == (2, 1, 1, 2500)
    assert [f["period"] for f in out["failed"]] == ["2008-01-03"]
    assert len(slept) == 4


def test_a_failed_fetch_is_tried_again(mod):
    answers = [JobError("HTTP 502: fetch failed"), {"new_capture": True, "records": 14}]

    def call(app, path, timeout=None):
        a = answers.pop(0)
        if isinstance(a, Exception):
            raise a
        return a

    slept = []
    assert mod.capture("TD-SECURITIES", "1980-02", call, slept.append)["records"] == 14 and slept == [10]
