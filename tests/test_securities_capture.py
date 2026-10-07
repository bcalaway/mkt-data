"""Treasury securities sources (phase 3): captured raw by period, then parsed into near-raw."""

import json
from datetime import date, datetime
from decimal import Decimal

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select

from app import db, jobs
from app.calendars import service
from app.calendars.parsed import ParseError
from app.config import Settings
from app.main import app
from app.models import Capture, Observation, SourceCheck
from app.securities import sources as sec
from tests.conftest import FIXTURES

client = TestClient(app)
TOKEN = "test-token"
NOW = datetime(2026, 10, 6, 19, 15, tzinfo=sec.EASTERN)

TD_JSON = json.dumps([
    {"cusip": "91282CNT4", "issueDate": "2026-10-15T00:00:00", "auctionDate": "2026-10-08T00:00:00",
     "securityType": "Note", "securityTerm": "10-Year", "interestRate": "4.250000", "corpusCusip": "912821AB1"},
]).encode()
TD_EMPTY = b"[]"
FD_EMPTY = json.dumps({"data": [], "meta": {"count": 0, "total-pages": 1}}).encode()
PRICES_CSV = b"912797KX4,MARKET BASED BILL,0.000000,10/09/2026,,99.910000,99.912000,99.911000\n"
PRICES_OCT5 = (FIXTURES / "td_prices_2026_10_05_capture1270.html").read_bytes()
BLS_2026 = (FIXTURES / "bls_cpi_2026_capture1267.json").read_bytes()


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
    assert all(src.spec.parse is not None for src in sec.SOURCES.values())


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
        assert r["new_capture"] and r["parsed"] and r["added"] == 1 and r["content_type"] == "application/json"
        again = sec.run_capture(s, "TD-SECURITIES", "2026-10", _fetcher(TD_JSON))
        assert not again["new_capture"] and again["capture_id"] == r["capture_id"] and again["added"] == 0
        other = sec.run_capture(s, "TD-SECURITIES", "2026-09", _fetcher(TD_EMPTY))
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
        return _fetcher(PRICES_OCT5, "text/html")

    monkeypatch.setattr(sec, "post_fedinvest", fake)
    with db.session() as s:
        r = sec.run_capture(s, "TD-PRICES", "2026-10-05")
    assert forms == ["2026-10-05"] and r["new_capture"] and r["period"] == "2026-10-05"
    assert r["values"] == 1359 and r["last_date"] == "2026-10-05"


FORM_PAGE = b'<form method="post"><input type="date" name="priceDate"/><input type="hidden" name="_csrf" value="tok-123"/></form>'


class _Client:
    """Stands in for httpx2.Client: records the GET and POST, answers from `pages`."""

    def __init__(self, pages, log):
        self.pages, self.log = pages, log

    def __call__(self, **kw):
        self.log.append(("client", kw["headers"]["User-Agent"]))
        return self

    def __enter__(self):
        return self

    def __exit__(self, *a):
        return False

    def _resp(self, key):
        status, body = self.pages[key]
        return type("R", (), {"status_code": status, "content": body, "headers": {"content-type": "text/html"}})()

    def get(self, url):
        self.log.append(("get", url))
        return self._resp("get")

    def post(self, url, data, headers):
        self.log.append(("post", url, data, headers["Referer"]))
        return self._resp("post")


def test_fedinvest_reads_the_form_then_posts(monkeypatch):
    log = []
    monkeypatch.setattr(sec.httpx2, "Client", _Client({"get": (200, FORM_PAGE), "post": (200, b"<table>prices</table>")}, log))
    assert sec.post_fedinvest("2026-03-09")(sec.TD_PRICES_URL) == (200, "text/html", b"<table>prices</table>")
    assert log[0] == ("client", service.USER_AGENT)
    assert log[1] == ("get", sec.TD_PRICES_URL)
    assert log[2] == ("post", sec.TD_PRICES_URL,
                      {"priceDate": "2026-03-09", "submit": "Show Prices", "_csrf": "tok-123"}, sec.TD_PRICES_URL)


def test_fedinvest_token_either_attribute_order():
    m = sec.CSRF.search(b'<input value="abc" type="hidden" name="_csrf">')
    assert (m.group(1) or m.group(2)) == b"abc"


def test_fedinvest_errors_are_fetch_errors(monkeypatch):
    monkeypatch.setattr(sec.httpx2, "Client", _Client({"get": (200, FORM_PAGE), "post": (403, b"")}, []))
    with pytest.raises(service.SourceFetchError, match="HTTP 403"):
        sec.post_fedinvest("2026-03-09")(sec.TD_PRICES_URL)
    monkeypatch.setattr(sec.httpx2, "Client", _Client({"get": (200, b"<form></form>"), "post": (200, b"")}, []))
    with pytest.raises(service.SourceFetchError, match="no CSRF token"):
        sec.post_fedinvest("2026-03-09")(sec.TD_PRICES_URL)


def test_bls_ignores_its_response_time(migrated_db):
    def bls(ms):
        row = {"year": "2026", "period": "M08", "value": "334.980"}
        return json.dumps({"status": "REQUEST_SUCCEEDED", "responseTime": ms, "message": [],
                           "Results": {"series": [{"seriesID": "CUUR0000SA0", "data": [row]}]}}).encode()

    with db.session() as s:
        first = sec.run_capture(s, "BLS-CPI", "2026", _fetcher(bls(81)))
        same = sec.run_capture(s, "BLS-CPI", "2026", _fetcher(bls(64)))
        assert first["new_capture"] and not same["new_capture"]
        detail = s.scalars(select(SourceCheck.detail).order_by(SourceCheck.id.desc()).limit(1)).one()
        assert "content identical" in detail
        changed = json.loads(bls(70))
        changed["Results"]["series"][0]["data"].append({"year": "2026", "period": "M09", "value": "335.5"})
        r = sec.run_capture(s, "BLS-CPI", "2026", _fetcher(json.dumps(changed).encode()))
        assert r["new_capture"] and r["added"] == 1
        # Unreadable JSON is never "the same": kept as a new capture, and its parse fails.
        with pytest.raises(ParseError):
            sec.run_capture(s, "BLS-CPI", "2026", _fetcher(b"<html>throttled</html>"))
        assert s.scalar(select(Capture.id).order_by(Capture.id.desc()).limit(1)) == 3
        check = s.scalars(select(SourceCheck).order_by(SourceCheck.id.desc()).limit(1)).one()
        assert check.parse_outcome == "error" and "not JSON" in check.parse_detail
        # The values from the last good capture stand.
        assert s.scalar(select(Observation.value).where(Observation.as_of == date(2026, 9, 1),
                                                        Observation.valid_to.is_(None))) == Decimal("335.5")


def test_empty_answer_is_a_fetch_error(migrated_db):
    with db.session() as s, pytest.raises(service.SourceFetchError, match="empty response"):
        sec.run_capture(s, "FD-AUCTIONS", "2026-10", _fetcher(b""))


def test_job_endpoint(token, migrated_db, monkeypatch):
    monkeypatch.setattr(service, "fetch", _fetcher(TD_JSON))
    assert client.post("/jobs/securities/NOPE/capture", headers=_auth()).status_code == 404
    assert client.post("/jobs/securities/td-securities/capture?period=2026-10-06", headers=_auth()).status_code == 400
    r = client.post("/jobs/securities/td-securities/capture?period=2026-10", headers=_auth())
    assert r.status_code == 200, r.text
    assert r.json()["source"] == "TD-SECURITIES" and r.json()["new_capture"] and r.json()["records"] == 1
    # A record outside the month asked for: the capture is kept, the parse refused.
    assert client.post("/jobs/securities/td-securities/capture?period=2026-09", headers=_auth()).status_code == 422
    # Default period: the current month.
    monkeypatch.setattr(service, "fetch", _fetcher(FD_EMPTY))
    r = client.post("/jobs/securities/FD-AUCTIONS/capture", headers=_auth())
    assert r.status_code == 200 and len(r.json()["period"]) == 7 and r.json()["records"] == 0

    def down(url):
        raise service.SourceFetchError(f"{url}: HTTP 404")

    monkeypatch.setattr(service, "fetch", down)
    assert client.post("/jobs/securities/FD-MSPD-STRIPS/capture?period=2026-09", headers=_auth()).status_code == 502

    caps = client.get("/jobs/captures", params={"source": "td-securities"}, headers=_auth()).json()["captures"]
    assert [(c["period"], c["parsed"], c["applied"]) for c in caps] == [("2026-09", True, False), ("2026-10", True, True)]
    r = client.post("/jobs/securities/td-securities/rebuild", headers=_auth())
    assert r.status_code == 200 and r.json()["current_records"] == 1 and len(r.json()["parse_failed"]) == 1


def test_capture_text_reads_json_and_csv(token, migrated_db, monkeypatch):
    monkeypatch.setattr(service, "fetch", _fetcher(TD_JSON))
    client.post("/jobs/securities/TD-SECURITIES/capture?period=2026-10", headers=_auth())
    monkeypatch.setattr(sec, "post_fedinvest", lambda period: _fetcher(PRICES_CSV, "text/csv"))
    # Not FedInvest's page: the parse fails (422), the capture stays and has a text view.
    assert client.post("/jobs/securities/TD-PRICES/capture?period=2026-10-02", headers=_auth()).status_code == 422

    j = client.get("/jobs/captures/1/text", params={"contains": "corpusCusip"},
                   headers={"Authorization": "Bearer read-token"}).json()
    assert j["view"] == "json" and j["matches"] == 1 and '"corpusCusip": "912821AB1"' in j["lines"][0]["text"]
    c = client.get("/jobs/captures/2/text", headers=_auth()).json()
    assert c["view"] == "text" and c["lines"][0]["text"].startswith("912797KX4,MARKET BASED BILL")
    assert client.get("/jobs/captures/1/text", params={"embedded": True}, headers=_auth()).status_code == 415


def test_metrics_label_the_new_sources(migrated_db):
    with db.session() as s:
        sec.run_capture(s, "BLS-CPI", "2026", _fetcher(BLS_2026))
    body = client.get("/metrics").text
    assert 'mkt_data_source_captures{calendar="FED",source="BLS-CPI",kind="published"} 1' in body
