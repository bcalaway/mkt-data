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


def test_nyse_capture_via_the_api(token, migrated_db, nyse_html, monkeypatch):
    monkeypatch.setattr(service, "fetch", lambda url: (200, "text/html", nyse_html))
    r = client.post("/jobs/calendars/nyse/capture", headers=_auth())
    assert r.status_code == 200, r.text
    assert r.json()["calendar"] == "NYSE" and r.json()["years"] == [2026, 2027, 2028]
    r = client.get("/jobs/calendars/NYSE/business-day", params={"on": "2026-11-27"}, headers=_auth())
    assert r.json()["close_time"] == "13:00" and r.json()["holiday"] == "Thanksgiving Day (early close)"


def test_captures_list_and_raw_body(token, migrated_db, fed_html, sifma_html, monkeypatch):
    for name, html in [("FED", fed_html), ("SIFMA-US", sifma_html)]:
        monkeypatch.setattr(service, "fetch", lambda url, html=html: (200, "text/html; charset=utf-8", html))
        assert client.post(f"/jobs/calendars/{name}/capture", headers=_auth()).status_code == 200

    r = client.get("/jobs/captures", headers=_auth())
    caps = r.json()["captures"]
    assert [c["source"] for c in caps] == ["SIFMA-US-HOLIDAYS", "FED-K8"]  # newest first
    only = client.get("/jobs/captures", params={"calendar": "sifma-us"}, headers=_auth()).json()["captures"]
    assert len(only) == 1 and only[0]["size_bytes"] == len(sifma_html)
    assert client.get("/jobs/captures", params={"source": "fed-k8"}, headers=_auth()).json()["captures"][0][
        "source"
    ] == "FED-K8"

    r = client.get(f"/jobs/captures/{only[0]['id']}", headers=_auth())
    assert r.status_code == 200 and r.content == sifma_html  # byte for byte
    assert r.headers["content-type"] == "text/html; charset=utf-8"
    assert r.headers["content-disposition"].startswith("attachment;")
    assert r.headers["x-capture-sha256"] == only[0]["sha256"]


def test_captures_need_the_token_and_exist(token, migrated_db):
    assert client.get("/jobs/captures/1").status_code == 401
    assert client.get("/jobs/captures/999", headers=_auth()).status_code == 404
    assert client.get("/jobs/captures", params={"calendar": "nope"}, headers=_auth()).status_code == 404
    r = client.get("/jobs/captures", params={"calendar": "FED", "source": "FED-K8"}, headers=_auth())
    assert r.status_code == 400
