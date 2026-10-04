"""Treasury CMT sources kept raw, one capture per source and month (app/rates/sources.py)."""

from datetime import datetime

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select

from app import db, jobs
from app.calendars import service
from app.config import Settings
from app.main import app
from app.models import Capture, SourceCheck
from app.rates import sources as rates


def _fetcher(seen: list, body: bytes = b"<feed/>", ctype: str = "application/xml"):
    def fetch(url):
        seen.append(url)
        return 200, ctype, body

    return fetch


def test_urls_for_a_month():
    assert rates.SOURCES["UST-PAR"].url("2026-02").endswith("field_tdr_date_value_month=202602")
    h15 = rates.SOURCES["H15-TCM"].url("2024-02")
    assert "from=02/01/2024&to=02/29/2024" in h15 and "series=bf17364827e38702b42a58cf8eaa3f78" in h15
    assert "from=12/01/2025&to=12/31/2025" in rates.SOURCES["H15-TCM"].url("2025-12")


def test_periods_are_checked():
    assert rates.check_period("UST-PAR", "1990-01") == "1990-01"
    for bad in ("1989-12", "2026-13", "2026-1", "soon", "2999-01"):
        with pytest.raises(rates.BadPeriod):
            rates.check_period("UST-PAR", bad)
    assert rates.check_period("H15-TCM", "1962-01") == "1962-01"


def test_current_period_is_new_york_time():
    assert rates.current_period(datetime(2026, 10, 31, 23, 0, tzinfo=rates.EASTERN)) == "2026-10"


def test_one_capture_per_source_and_month(migrated_db):
    seen = []
    with db.session() as s:
        first = rates.run_capture(s, "UST-PAR", "2026-09", _fetcher(seen, b"<feed>sep</feed>"))
        again = rates.run_capture(s, "UST-PAR", "2026-09", _fetcher(seen, b"<feed>sep</feed>"))
        other = rates.run_capture(s, "UST-PAR", "2026-10", _fetcher(seen, b"<feed>sep</feed>"))
        grown = rates.run_capture(s, "UST-PAR", "2026-09", _fetcher(seen, b"<feed>sep+1</feed>"))
    assert first["new_capture"] is True and first["parsed"] is False
    assert again["new_capture"] is False and again["capture_id"] == first["capture_id"]
    # The same bytes in another month are that month's own capture.
    assert other["new_capture"] is True and other["capture_id"] != first["capture_id"]
    assert grown["new_capture"] is True
    with db.session() as s:
        periods = s.scalars(select(Capture.period).order_by(Capture.id)).all()
        checks = s.scalars(select(SourceCheck.period).order_by(SourceCheck.id)).all()
    assert periods == ["2026-09", "2026-10", "2026-09"]
    assert checks == ["2026-09", "2026-09", "2026-10", "2026-09"]
    assert seen[0].endswith("202609") and seen[2].endswith("202610")


def test_calendar_sources_still_dedupe_whole(migrated_db, fed_html):
    with db.session() as s:
        service.run_capture(s, "FED", lambda url: (200, "text/html", fed_html))
        rates.run_capture(s, "UST-PAR", "2026-09", _fetcher([], fed_html))  # same bytes, other source
        again = service.run_capture(s, "FED", lambda url: (200, "text/html", fed_html))["sources"][0]
    assert again["new_capture"] is False


client = TestClient(app)


def test_capture_job(migrated_db, monkeypatch):
    monkeypatch.setattr(jobs, "settings", Settings(airflow_token="t"))
    monkeypatch.setattr(service, "fetch", _fetcher([], b"Series Description,x\n2026-09-01,4.0\n", "text/csv"))
    auth = {"Authorization": "Bearer t"}
    r = client.post("/jobs/rates/h15-tcm/capture?period=2026-09", headers=auth)
    assert r.status_code == 200, r.text
    assert r.json()["source"] == "H15-TCM" and r.json()["period"] == "2026-09"
    assert client.post("/jobs/rates/H15-TCM/capture", headers=auth).json()["period"] == rates.current_period()
    assert client.post("/jobs/rates/NOPE/capture", headers=auth).status_code == 404
    assert client.post("/jobs/rates/UST-PAR/capture?period=1989-12", headers=auth).status_code == 400
    listed = client.get("/jobs/captures?source=H15-TCM", headers=auth).json()["captures"]
    assert listed[-1]["period"] == "2026-09" and listed[-1]["parsed"] is False


def test_fetch_failure_is_a_502(migrated_db, monkeypatch):
    monkeypatch.setattr(jobs, "settings", Settings(airflow_token="t"))

    def boom(url):
        raise service.SourceFetchError(f"{url}: HTTP 503")

    monkeypatch.setattr(service, "fetch", boom)
    r = client.post("/jobs/rates/UST-PAR/capture?period=2026-09", headers={"Authorization": "Bearer t"})
    assert r.status_code == 502


def test_metrics_label_the_cmt_sources(migrated_db):
    with db.session() as s:
        rates.run_capture(s, "UST-PAR", "2026-09", _fetcher([]))
    text = client.get("/metrics").text
    assert 'mkt_data_source_captures{calendar="SIFMA-US",source="UST-PAR",kind="published"} 1' in text
