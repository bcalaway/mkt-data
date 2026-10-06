"""Treasury securities sources (phase 3, step 1): captured raw by period, no parsers yet."""

import json
from datetime import datetime

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select

from app import db, jobs
from app.calendars import service
from app.config import Settings
from app.main import app
from app.models import Capture, SourceCheck
from app.securities import sources as sec

client = TestClient(app)
TOKEN = "test-token"
NOW = datetime(2026, 10, 6, 19, 15, tzinfo=sec.EASTERN)

TD_JSON = json.dumps([
    {"cusip": "91282CNT4", "issueDate": "2026-10-15T00:00:00", "securityType": "Note", "securityTerm": "10-Year",
     "interestRate": "4.250000", "corpusCusip": "912821AB1"},
]).encode()
PRICES_CSV = b"912797KX4,MARKET BASED BILL,0.000000,10/09/2026,,99.910000,99.912000,99.911000\n"


def _auth():
    return {"Authorization": f"Bearer {TOKEN}"}


@pytest.fixture
def token(monkeypatch):
    monkeypatch.setattr(jobs, "settings", Settings(airflow_token=TOKEN, read_token="read-token"))


def _fetcher(body: bytes, ctype: str = "application/json", seen: list | None = None):
    def fetch(url):
        if seen is not None:
            seen.append(url)
        return 200, ctype, body

    return fetch


def test_urls_by_period():
    td = sec.SOURCES["TD-SECURITIES"].url("2024-02")
    assert "startDate=02/01/2024&endDate=02/29/2024" in td and "dateFieldName=auctionDate" in td
    assert "auction_date:gte:2025-12-01,auction_date:lte:2025-12-31" in sec.SOURCES["FD-AUCTIONS"].url("2025-12")
    assert "record_date:gte:2026-09-01,record_date:lte:2026-09-30" in sec.SOURCES["FD-MSPD-STRIPS"].url("2026-09")
    assert sec.SOURCES["BLS-CPI"].url("2026").endswith("startyear=2026&endyear=2026")
    assert sec.SOURCES["TD-PRICES"].url("2026-10-06") == sec.TD_PRICES_URL
    assert all(src.spec.parse is None for src in sec.SOURCES.values())


def test_periods_are_checked_by_kind():
    assert sec.check_period("TD-SECURITIES", "2026-11", NOW) == "2026-11"  # a month ahead: announcements
    assert sec.check_period("TD-PRICES", "2026-10-06", NOW) == "2026-10-06"
    assert sec.check_period("BLS-CPI", "1913", NOW) == "1913"
    bad = [
        ("TD-SECURITIES", "2026-12"), ("TD-SECURITIES", "1978-12"), ("TD-SECURITIES", "2026-1"),
        ("TD-SECURITIES", "2026-10-06"), ("TD-PRICES", "2026-10-07"), ("TD-PRICES", "2026-10"),
        ("TD-PRICES", "2026-1-6"), ("FD-MSPD-STRIPS", "2026-11"), ("BLS-CPI", "2027"), ("BLS-CPI", "26"),
        ("BLS-CPI", "soon"),
    ]
    for name, period in bad:
        with pytest.raises(sec.BadPeriod):
            sec.check_period(name, period, NOW)


def test_current_period_is_new_york_time():
    late = datetime(2026, 12, 31, 23, 30, tzinfo=sec.EASTERN)
    assert sec.current_period("day", late) == "2026-12-31"
    assert sec.current_period("month", late) == "2026-12"
    assert sec.current_period("year", late) == "2026"


def test_capture_keeps_raw_and_dedupes_per_period(migrated_db):
    seen = []
    with db.session() as s:
        r = sec.run_capture(s, "TD-SECURITIES", "2026-10", _fetcher(TD_JSON, seen=seen))
        assert r["new_capture"] and r["parsed"] is False and r["content_type"] == "application/json"
        again = sec.run_capture(s, "TD-SECURITIES", "2026-10", _fetcher(TD_JSON))
        assert not again["new_capture"] and again["capture_id"] == r["capture_id"]
        other = sec.run_capture(s, "TD-SECURITIES", "2026-09", _fetcher(TD_JSON))
        assert other["new_capture"]  # same bytes, another period: its own capture
        periods = s.scalars(select(Capture.period).order_by(Capture.id)).all()
        outcomes = s.scalars(select(SourceCheck.outcome).order_by(SourceCheck.id)).all()
    assert periods == ["2026-10", "2026-09"]
    assert outcomes == ["new", "unchanged", "new"]
    assert seen[0].startswith("https://www.treasurydirect.gov/TA_WS/securities/search?format=json")


def test_prices_post_the_form(migrated_db, monkeypatch):
    forms = []

    def fake(period):
        forms.append(period)
        return _fetcher(PRICES_CSV, "text/csv")

    monkeypatch.setattr(sec, "post_fedinvest", fake)
    with db.session() as s:
        r = sec.run_capture(s, "TD-PRICES", "2026-10-02")
    assert forms == ["2026-10-02"] and r["new_capture"] and r["period"] == "2026-10-02"


def test_fedinvest_form_fields(monkeypatch):
    sent = {}

    class Resp:
        status_code, headers, content = 200, {"content-type": "text/csv"}, PRICES_CSV

    def post(url, data, **kw):
        sent.update(url=url, data=data, ua=kw["headers"]["User-Agent"])
        return Resp()

    monkeypatch.setattr(sec.httpx2, "post", post)
    assert sec.post_fedinvest("2026-03-09")(sec.TD_PRICES_URL) == (200, "text/csv", PRICES_CSV)
    assert sent["data"] == {"priceDateDay": "09", "priceDateMonth": "03", "priceDateYear": "2026",
                            "fileType": "csv", "csv": "CSV FORMAT"}
    assert sent["ua"] == service.USER_AGENT


def test_fedinvest_errors_are_fetch_errors(monkeypatch):
    class Resp:
        status_code, headers, content = 503, {}, b""

    monkeypatch.setattr(sec.httpx2, "post", lambda url, data, **kw: Resp())
    with pytest.raises(service.SourceFetchError, match="HTTP 503"):
        sec.post_fedinvest("2026-03-09")(sec.TD_PRICES_URL)


def test_bls_ignores_its_response_time(migrated_db):
    def bls(ms):
        return json.dumps({"status": "REQUEST_SUCCEEDED", "responseTime": ms, "message": [],
                           "Results": {"series": [{"seriesID": "CUUR0000SA0", "data": [{"year": "2026"}]}]}}).encode()

    with db.session() as s:
        first = sec.run_capture(s, "BLS-CPI", "2026", _fetcher(bls(81)))
        same = sec.run_capture(s, "BLS-CPI", "2026", _fetcher(bls(64)))
        assert first["new_capture"] and not same["new_capture"]
        detail = s.scalars(select(SourceCheck.detail).order_by(SourceCheck.id.desc()).limit(1)).one()
        assert "content identical" in detail
        changed = json.loads(bls(70))
        changed["Results"]["series"][0]["data"].append({"year": "2026", "period": "M09"})
        assert sec.run_capture(s, "BLS-CPI", "2026", _fetcher(json.dumps(changed).encode()))["new_capture"]
        # Unreadable JSON is never "the same".
        assert sec.run_capture(s, "BLS-CPI", "2026", _fetcher(b"<html>throttled</html>"))["new_capture"]


def test_empty_answer_is_a_fetch_error(migrated_db):
    with db.session() as s, pytest.raises(service.SourceFetchError, match="empty response"):
        sec.run_capture(s, "FD-AUCTIONS", "2026-10", _fetcher(b""))


def test_job_endpoint(token, migrated_db, monkeypatch):
    monkeypatch.setattr(service, "fetch", _fetcher(TD_JSON))
    assert client.post("/jobs/securities/NOPE/capture", headers=_auth()).status_code == 404
    assert client.post("/jobs/securities/td-securities/capture?period=2026-10-06", headers=_auth()).status_code == 400
    r = client.post("/jobs/securities/td-securities/capture?period=2026-09", headers=_auth())
    assert r.status_code == 200, r.text
    assert r.json()["source"] == "TD-SECURITIES" and r.json()["new_capture"]
    # Default period: the current month.
    r = client.post("/jobs/securities/FD-AUCTIONS/capture", headers=_auth())
    assert r.status_code == 200 and len(r.json()["period"]) == 7

    def down(url):
        raise service.SourceFetchError(f"{url}: HTTP 404")

    monkeypatch.setattr(service, "fetch", down)
    assert client.post("/jobs/securities/FD-MSPD-STRIPS/capture?period=2026-09", headers=_auth()).status_code == 502

    caps = client.get("/jobs/captures", params={"source": "td-securities"}, headers=_auth()).json()["captures"]
    assert caps[0]["period"] == "2026-09" and caps[0]["parsed"] is False and not caps[0]["applied"]


def test_capture_text_reads_json_and_csv(token, migrated_db, monkeypatch):
    monkeypatch.setattr(service, "fetch", _fetcher(TD_JSON))
    client.post("/jobs/securities/TD-SECURITIES/capture?period=2026-10", headers=_auth())
    monkeypatch.setattr(sec, "post_fedinvest", lambda period: _fetcher(PRICES_CSV, "text/csv"))
    client.post("/jobs/securities/TD-PRICES/capture?period=2026-10-02", headers=_auth())

    j = client.get("/jobs/captures/1/text", params={"contains": "corpusCusip"},
                   headers={"Authorization": "Bearer read-token"}).json()
    assert j["view"] == "json" and j["matches"] == 1 and '"corpusCusip": "912821AB1"' in j["lines"][0]["text"]
    c = client.get("/jobs/captures/2/text", headers=_auth()).json()
    assert c["view"] == "text" and c["lines"][0]["text"].startswith("912797KX4,MARKET BASED BILL")
    assert client.get("/jobs/captures/1/text", params={"embedded": True}, headers=_auth()).status_code == 415


def test_metrics_label_the_new_sources(migrated_db):
    with db.session() as s:
        sec.run_capture(s, "BLS-CPI", "2026", _fetcher(b'{"status": "REQUEST_SUCCEEDED"}'))
    body = client.get("/metrics").text
    assert 'mkt_data_source_captures{calendar="FED",source="BLS-CPI",kind="published"} 1' in body
