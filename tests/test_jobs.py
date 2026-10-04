import pytest
from fastapi.testclient import TestClient

from app import jobs
from app.calendars import service
from app.config import Settings
from app.main import app

client = TestClient(app)
TOKEN = "test-token"


@pytest.fixture
def token(monkeypatch):
    monkeypatch.setattr(jobs, "settings", Settings(airflow_token=TOKEN))


def _auth(t=TOKEN):
    return {"Authorization": f"Bearer {t}"}


def test_jobs_disabled_without_a_token():
    r = client.post("/jobs/calendars/FED/capture", headers=_auth())
    assert r.status_code == 503


def test_wrong_or_missing_token(token):
    assert client.post("/jobs/calendars/FED/capture", headers=_auth("nope")).status_code == 401
    assert client.post("/jobs/calendars/FED/capture").status_code == 401


def test_unknown_calendar(token):
    assert client.post("/jobs/calendars/NOPE/capture", headers=_auth()).status_code == 404


def test_capture_and_business_day(token, migrated_db, fed_html, monkeypatch):
    monkeypatch.setattr(service, "fetch", lambda url: (200, "text/html", fed_html))
    r = client.post("/jobs/calendars/fed/capture", headers=_auth())
    assert r.status_code == 200, r.text
    assert r.json()["added"] == 50
    r = client.get("/jobs/calendars/FED/business-day", params={"on": "2027-07-05"}, headers=_auth())
    assert r.status_code == 200 and r.json()["business_day"] is False
    r = client.get("/jobs/calendars/FED/business-day", params={"on": "2031-03-04"}, headers=_auth())
    assert r.status_code == 409


def test_fetch_failure_is_a_502(token, migrated_db, monkeypatch):
    def boom(url):
        raise service.SourceFetchError("down")

    monkeypatch.setattr(service, "fetch", boom)
    assert client.post("/jobs/calendars/FED/capture", headers=_auth()).status_code == 502


def test_parse_failure_is_a_422(token, migrated_db, fed_html, monkeypatch):
    broken = fed_html.replace(b"<td>July 4**</td>", b"<td>July 4</td>")
    monkeypatch.setattr(service, "fetch", lambda url: (200, "text/html", broken))
    r = client.post("/jobs/calendars/FED/capture", headers=_auth())
    assert r.status_code == 422 and "raw capture kept" in r.json()["detail"]


def test_sifma_capture_via_the_api(token, migrated_db, sifma_html, monkeypatch):
    monkeypatch.setattr(service, "fetch", lambda url: (200, "text/html", sifma_html))
    r = client.post("/jobs/calendars/sifma-us/capture", headers=_auth())
    assert r.status_code == 200, r.text
    assert r.json()["calendar"] == "SIFMA-US"
    r = client.get("/jobs/calendars/SIFMA-US/business-day", params={"on": "2026-12-24"}, headers=_auth())
    assert r.json()["close_time"] == "14:00" and r.json()["business_day"] is True
