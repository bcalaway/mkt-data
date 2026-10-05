"""Treasury CMT sources: one capture per source and month, parsed into near-raw observations."""

from datetime import date, datetime
from decimal import Decimal

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import func, select

from app import db, jobs
from app.calendars import service
from app.calendars.parsed import ParseError
from app.config import Settings
from app.main import app
from app.models import Capture, Observation, SourceCheck
from app.rates import sources as rates
from tests.conftest import FIXTURES

UST_SEP = (FIXTURES / "ust_par_2026_09_capture31.xml").read_bytes()
UST_OCT = (FIXTURES / "ust_par_2026_10_capture32.xml").read_bytes()
H15_SEP = (FIXTURES / "h15_tcm_2026_09_capture30.csv").read_bytes()


def _fetcher(body: bytes, seen: list | None = None, ctype: str = "text/xml"):
    def fetch(url):
        if seen is not None:
            seen.append(url)
        return 200, ctype, body

    return fetch


def _current(s, key=None, day=None):
    q = select(Observation).where(Observation.valid_to.is_(None))
    if key:
        q = q.where(Observation.source_key == key)
    if day:
        q = q.where(Observation.as_of == day)
    return s.scalars(q).all()


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


def test_a_capture_records_its_months_observations(migrated_db):
    with db.session() as s:
        out = rates.run_capture(s, "UST-PAR", "2026-09", _fetcher(UST_SEP))
    assert out["new_capture"] is True and out["values"] == 21 * 14 and out["days"] == 21 and out["added"] == 21 * 14
    assert out["last_date"] == "2026-09-30"
    with db.session() as s:
        ten = _current(s, "BC_10YEAR", date(2026, 9, 1))
        assert len(ten) == 1 and ten[0].value == Decimal("4.79") and ten[0].unit == "percent"
        assert ten[0].period == "2026-09" and ten[0].field == "yield"
        check = s.scalar(select(SourceCheck).order_by(SourceCheck.id.desc()))
        assert check.parse_outcome == "ok" and check.period == "2026-09"


def test_one_capture_per_source_and_month(migrated_db):
    seen = []
    with db.session() as s:
        first = rates.run_capture(s, "UST-PAR", "2026-09", _fetcher(UST_SEP, seen))
        again = rates.run_capture(s, "UST-PAR", "2026-09", _fetcher(UST_SEP, seen))
        other = rates.run_capture(s, "UST-PAR", "2026-10", _fetcher(UST_OCT, seen))
    assert again["new_capture"] is False and again["capture_id"] == first["capture_id"] and again["added"] == 0
    assert other["new_capture"] is True and other["days"] == 2
    with db.session() as s:
        assert s.scalars(select(Capture.period).order_by(Capture.id)).all() == ["2026-09", "2026-10"]
        assert len(_current(s)) == 21 * 14 + 2 * 14  # October's capture didn't touch September
    assert seen[0].endswith("202609") and seen[2].endswith("202610")


def test_a_revision_keeps_history_and_a_dropped_value_is_closed(migrated_db):
    with db.session() as s:
        rates.run_capture(s, "UST-PAR", "2026-10", _fetcher(UST_OCT))
    revised = UST_OCT.replace(
        b'<d:BC_10YEAR m:type="Edm.Double">5.24</d:BC_10YEAR>', b'<d:BC_10YEAR m:type="Edm.Double">5.25</d:BC_10YEAR>', 1
    ).replace(b'<d:BC_1_5MONTH m:type="Edm.Double">4.10</d:BC_1_5MONTH>', b"", 1)
    with db.session() as s:
        out = rates.run_capture(s, "UST-PAR", "2026-10", _fetcher(revised))
    assert out["new_capture"] is True and out["changed"] == 1 and out["removed"] == 1 and out["added"] == 0
    with db.session() as s:
        rows = s.scalars(select(Observation).where(
            Observation.source_key == "BC_10YEAR", Observation.as_of == date(2026, 10, 1)).order_by(Observation.id)).all()
        assert [(r.value, r.valid_to is None) for r in rows] == [(Decimal("5.24"), False), (Decimal("5.25"), True)]
        assert rows[0].valid_to == rows[1].valid_from  # the revising capture's fetch time
        assert _current(s, "BC_1_5MONTH", date(2026, 10, 1)) == []


def test_a_page_that_doesnt_parse_keeps_the_raw_capture(migrated_db):
    with db.session() as s, pytest.raises(ParseError):
        rates.run_capture(s, "UST-PAR", "2026-09", _fetcher(b"<html>Treasury is down for maintenance</html>"))
    with db.session() as s:
        assert s.scalar(select(func.count()).select_from(Capture)) == 1
        assert _current(s) == []
        assert s.scalar(select(SourceCheck.parse_outcome)) == "error"


def test_values_outside_the_month_are_rejected(migrated_db):
    with db.session() as s, pytest.raises(ParseError, match="outside the capture's month"):
        rates.run_capture(s, "UST-PAR", "2026-08", _fetcher(UST_SEP))


def test_an_empty_response_is_a_fetch_error_not_a_capture(migrated_db):
    with db.session() as s, pytest.raises(service.SourceFetchError, match="empty response"):
        rates.run_capture(s, "H15-TCM", "2026-10", _fetcher(b""))
    with db.session() as s:
        assert s.scalar(select(func.count()).select_from(Capture)) == 0
        assert s.scalar(select(SourceCheck.outcome)) == "error"


def test_rebuild_replays_every_capture_to_the_same_rows(migrated_db):
    revised = UST_OCT.replace(b">5.24</d:BC_10YEAR>", b">5.25</d:BC_10YEAR>", 1)
    with db.session() as s:
        rates.run_capture(s, "UST-PAR", "2026-09", _fetcher(UST_SEP))
        rates.run_capture(s, "UST-PAR", "2026-10", _fetcher(UST_OCT))
        rates.run_capture(s, "UST-PAR", "2026-10", _fetcher(revised))

    def snapshot():
        with db.session() as s:
            return sorted((r.source_key, r.as_of, r.value, r.capture_id, r.valid_from, r.valid_to)
                          for r in s.scalars(select(Observation)))

    before = snapshot()
    with db.session() as s:
        out = rates.run_rebuild(s, "UST-PAR")
    assert snapshot() == before
    assert out["captures"] == 3 and out["applied"] == 3 and out["current_values"] == 23 * 14
    assert (out["first_date"], out["last_date"]) == (date(2026, 9, 1), date(2026, 10, 2))


def test_h15_capture(migrated_db):
    with db.session() as s:
        out = rates.run_capture(s, "H15-TCM", "2026-09", _fetcher(H15_SEP, ctype="text/csv"))
        assert out["values"] == 21 * 11
        assert _current(s, "RIFLGFCY10_N.B", date(2026, 9, 1))[0].value == Decimal("4.79")


def test_calendar_sources_still_dedupe_whole(migrated_db, fed_html):
    with db.session() as s:
        service.run_capture(s, "FED", lambda url: (200, "text/html", fed_html))
        again = service.run_capture(s, "FED", lambda url: (200, "text/html", fed_html))["sources"][0]
    assert again["new_capture"] is False


client = TestClient(app)
AUTH = {"Authorization": "Bearer t"}


def test_capture_and_rebuild_jobs(migrated_db, monkeypatch):
    monkeypatch.setattr(jobs, "settings", Settings(airflow_token="t"))
    monkeypatch.setattr(service, "fetch", _fetcher(H15_SEP, ctype="text/csv"))
    r = client.post("/jobs/rates/h15-tcm/capture?period=2026-09", headers=AUTH)
    assert r.status_code == 200, r.text
    assert r.json()["source"] == "H15-TCM" and r.json()["values"] == 231
    assert client.post("/jobs/rates/NOPE/capture", headers=AUTH).status_code == 404
    assert client.post("/jobs/rates/UST-PAR/capture?period=1989-12", headers=AUTH).status_code == 400
    listed = client.get("/jobs/captures?source=H15-TCM", headers=AUTH).json()["captures"]
    assert listed[0]["period"] == "2026-09" and listed[0]["parsed"] is True and listed[0]["applied"] is True
    r = client.post("/jobs/rates/H15-TCM/rebuild", headers=AUTH)
    assert r.status_code == 200 and r.json()["current_values"] == 231


def test_parse_failure_is_a_422(migrated_db, monkeypatch):
    monkeypatch.setattr(jobs, "settings", Settings(airflow_token="t"))
    monkeypatch.setattr(service, "fetch", _fetcher(b"<html>maintenance</html>"))
    r = client.post("/jobs/rates/UST-PAR/capture?period=2026-09", headers=AUTH)
    assert r.status_code == 422 and "raw capture kept" in r.json()["detail"]


def test_fetch_failure_is_a_502(migrated_db, monkeypatch):
    monkeypatch.setattr(jobs, "settings", Settings(airflow_token="t"))

    def boom(url):
        raise service.SourceFetchError(f"{url}: HTTP 503")

    monkeypatch.setattr(service, "fetch", boom)
    assert client.post("/jobs/rates/UST-PAR/capture?period=2026-09", headers=AUTH).status_code == 502


def test_metrics_label_the_cmt_sources(migrated_db):
    with db.session() as s:
        rates.run_capture(s, "UST-PAR", "2026-09", _fetcher(UST_SEP))
    text = client.get("/metrics").text
    assert 'mkt_data_source_captures{calendar="SIFMA-US",source="UST-PAR",kind="published"} 1' in text
    assert 'mkt_data_source_parse_ok{calendar="SIFMA-US",source="UST-PAR",kind="published"} 1' in text
    # 2026-09-30 00:00 UTC: each key's latest date in the source's newest month.
    assert 'mkt_data_observation_last_date_timestamp_seconds{calendar="SIFMA-US",source="UST-PAR",key="BC_10YEAR"} 1790726400' in text
