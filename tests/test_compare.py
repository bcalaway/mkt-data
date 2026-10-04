"""Phase 2, step A4: comparing calendar-svc's calendars with calendar_day (app/calendars/compare.py)."""

from fastapi.testclient import TestClient

from app import db, jobs
from app.calendars import compare, service
from app.config import Settings
from app.main import app


def _as_calendar_svc(days, years):
    """What calendar-svc's Closes and Coverage would return for this calendar."""
    closes = [{"date": d, "status": st, "close_time": t, "holiday": h} for d, (st, t, h) in sorted(days.items())]
    coverage = [{"year": y, "source": src, "kind": kind} for y, (src, kind) in sorted(years.items())]
    return closes, coverage


def _captured(sifma_fetch, fed_html):
    with db.session() as s:
        service.run_capture(s, "SIFMA-US", sifma_fetch)
        service.run_capture(s, "FED", lambda url: (200, "text/html", fed_html))


def test_identical_calendars_are_equal(migrated_db, sifma_fetch, fed_html):
    _captured(sifma_fetch, fed_html)
    with db.session() as s:
        mirror = {name: _as_calendar_svc(*compare.ours(s, name)) for name in service.CALENDARS}
        out = compare.run(s, mirror.__getitem__)
    assert out["equal"] is True
    sifma = next(c for c in out["calendars"] if c["calendar"] == "SIFMA-US")
    assert sifma["days"]["ours"] == sifma["days"]["calendar_svc"] > 400
    assert sifma["days_that_differ_count"] == 0 and sifma["years_whose_kind_differs"] == []


def test_differences_are_listed(migrated_db, sifma_fetch, fed_html):
    _captured(sifma_fetch, fed_html)
    with db.session() as s:
        days, years = compare.ours(s, "SIFMA-US")
    days = dict(days)
    years = dict(years)
    gf = "2026-04-03"
    days[gf] = ("closed", "", days[gf][2])          # early close became a full close
    removed = min(days)
    del days[removed]                                # a day calendar-svc lacks
    days["2026-06-01"] = ("closed", "", "Made up")   # a day only calendar-svc has
    y = min(years)
    years[y] = (years[y][0], "projected")            # a year credited to the wrong kind
    with db.session() as s:
        out = compare.compare("SIFMA-US", compare.ours(s, "SIFMA-US"), compare.theirs(*_as_calendar_svc(days, years)))
    assert out["equal"] is False
    assert out["days_that_differ"][0]["date"] == gf and out["days_that_differ"][0]["mkt_data"][0] == "early_close"
    assert out["days_only_in_mkt_data"] == [removed]
    assert out["days_only_in_calendar_svc"] == ["2026-06-01"]
    assert [x["year"] for x in out["years_whose_kind_differs"]] == [y]


client = TestClient(app)


def test_compare_endpoint(migrated_db, fed_html, monkeypatch):
    monkeypatch.setattr(jobs, "settings", Settings(airflow_token="t"))
    with db.session() as s:
        service.run_capture(s, "FED", lambda url: (200, "text/html", fed_html))
        mirror = {name: _as_calendar_svc(*compare.ours(s, name)) for name in service.CALENDARS}
    monkeypatch.setattr(compare.CalendarSvc, "read", lambda self, name: mirror[name])
    r = client.post("/jobs/calendars/compare-with-calendar-svc", headers={"Authorization": "Bearer t"})
    assert r.status_code == 200, r.text
    assert r.json()["equal"] is True
    assert client.post("/jobs/calendars/compare-with-calendar-svc").status_code == 401
