"""Phase 4's sources (app/futures/sources.py): fixings and CFTC positioning, captured raw by period."""

import json
from datetime import datetime

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import func, select

from app import db, jobs, source_status
from app.calendars import service
from app.config import Settings
from app.futures import sources as fut
from app.main import app
from app.models import Capture, SourceCheck
from app.securities import sources as sec

client = TestClient(app)
TOKEN = "test-token"
NOW = datetime(2026, 10, 7, 19, 45, tzinfo=sec.EASTERN)

SOFR = json.dumps({"refRates": [
    {"effectiveDate": "2026-10-05", "type": "SOFR", "percentRate": 3.89, "percentPercentile1": 3.84,
     "percentPercentile25": 3.87, "percentPercentile75": 3.94, "percentPercentile99": 3.97, "volumeInBillions": 3007,
     "revisionIndicator": ""}]}).encode()
NO_RATES = b'{"refRates":[]}'
TFF = (b"market_and_exchange_names,report_date_as_yyyy_mm_dd,cftc_contract_market_code\n"
       b'"UST BOND - CHICAGO BOARD OF TRADE",2026-09-29T00:00:00.000,020601\n')
TFF_HEADER_ONLY = b"market_and_exchange_names,report_date_as_yyyy_mm_dd,cftc_contract_market_code\n"


def _fetcher(body: bytes, ctype: str = "application/json", seen: list | None = None):
    def fetch(url):
        if seen is not None:
            seen.append(url)
        return 200, ctype, body

    return fetch


def test_urls_by_period():
    assert fut.SOURCES["NYFED-SOFR"].url("2026-09") == (
        "https://markets.newyorkfed.org/api/rates/secured/sofr/search.json?startDate=2026-09-01&endDate=2026-09-30")
    assert "/unsecured/effr/search.json?startDate=2024-02-01&endDate=2024-02-29" in fut.SOURCES["NYFED-EFFR"].url("2024-02")
    assert "/secured/sofrai/" in fut.SOURCES["NYFED-SOFR-AVG"].url("2026-09")
    assert "rel=H10&" in fut.SOURCES["FRB-H10"].url("2026-09") and "from=09/01/2026&to=09/30/2026" in fut.SOURCES[
        "FRB-H10"].url("2026-09")
    assert fut.SOURCES["ECB-EXR"].url("2026-09").endswith("startPeriod=2026-09-01&endPeriod=2026-09-30&format=csvdata")
    tff = fut.SOURCES["CFTC-TFF"].url("2026-09-29")
    assert tff.startswith("https://publicreporting.cftc.gov/resource/gpe5-46if.csv?")
    assert "report_date_as_yyyy_mm_dd%3D%272026-09-29T00%3A00%3A00.000%27" in tff
    assert "/yw9f-hn96.csv?" in fut.SOURCES["CFTC-TFF-COMBINED"].url("2026-09-29")
    assert all(src.spec.parse is None and src.spec.pulls for src in fut.SOURCES.values())
    assert not set(fut.SOURCES) & set(sec.SOURCES)


def test_the_ddp_is_asked_again_when_it_answers_empty(monkeypatch):
    answers = [b"", b"", b"csv"]
    monkeypatch.setattr(service, "fetch", lambda url: (200, "text/csv", answers.pop(0)))
    assert fut.fetch_ddp("u", sleep=lambda s: None)[2] == b"csv"
    monkeypatch.setattr(service, "fetch", lambda url: (200, "text/csv", b""))
    with pytest.raises(service.SourceFetchError, match="empty response, 3 tries"):
        fut.fetch_ddp("u", sleep=lambda s: None)


def test_periods_are_checked():
    assert fut.check_period("NYFED-SOFR", "2018-04", NOW) == "2018-04"
    assert fut.check_period("CFTC-TFF", "2026-09-29", NOW) == "2026-09-29"
    for name, period in [("NYFED-SOFR", "2018-03"), ("NYFED-SOFR", "2026-11"), ("CFTC-TFF", "2026-09"),
                         ("ECB-EXR", "1998-12"), ("CFTC-TFF", "2026-10-08")]:
        with pytest.raises(sec.BadPeriod):
            fut.check_period(name, period, NOW)


def test_capture_keeps_raw_without_parsing(migrated_db, monkeypatch):
    seen = []
    monkeypatch.setattr(service, "fetch", _fetcher(SOFR, seen=seen))
    with db.session() as s:
        r = fut.run_capture(s, "NYFED-SOFR", "2026-10")
    assert r["new_capture"] and r["parsed"] is False and seen[0].endswith("startDate=2026-10-01&endDate=2026-10-31")
    with db.session() as s:
        assert not fut.run_capture(s, "NYFED-SOFR", "2026-10")["new_capture"]  # the same bytes: unchanged
        checks = s.scalars(select(SourceCheck).order_by(SourceCheck.id)).all()
        assert [c.outcome for c in checks] == ["new", "unchanged"] and {c.parse_outcome for c in checks} == {None}
        cap = s.scalars(select(Capture)).one()
        assert cap.period == "2026-10" and cap.body == SOFR
        state = next(x for x in source_status.list_sources(s) if x["name"] == "NYFED-SOFR")
        assert (state["group"], state["parsed"], state["captures"], state["dag"]) == (
            "futures", False, 1, "mkt_data__futures_sources_capture")


@pytest.mark.parametrize(("name", "period", "fetch"), [
    ("NYFED-EFFR", "2026-10", _fetcher(NO_RATES)),
    ("CFTC-TFF", "2026-10-06", _fetcher(TFF_HEADER_ONLY, "text/csv")),
])
def test_nothing_published_is_a_failed_fetch_not_a_capture(migrated_db, monkeypatch, name, period, fetch):
    monkeypatch.setattr(service, "fetch", fetch)
    with db.session() as s, pytest.raises(service.SourceFetchError, match=fut.NOT_PUBLISHED):
        fut.run_capture(s, name, period)
    with db.session() as s:
        assert s.scalar(select(func.count()).select_from(Capture)) == 0
        assert s.scalars(select(SourceCheck)).one().outcome == "error"


def test_the_ecb_404_is_nothing_published(migrated_db, monkeypatch):
    def fetch(url):
        raise service.SourceFetchError(f"{url}: HTTP 404")

    monkeypatch.setattr(service, "fetch", fetch)
    with db.session() as s, pytest.raises(service.SourceFetchError, match=fut.NOT_PUBLISHED):
        fut.run_capture(s, "ECB-EXR", "2026-10")


def test_a_cftc_report_is_kept(migrated_db, monkeypatch):
    monkeypatch.setattr(service, "fetch", _fetcher(TFF, "text/csv"))
    with db.session() as s:
        assert fut.run_capture(s, "CFTC-TFF", "2026-09-29")["new_capture"]


def test_job(migrated_db, monkeypatch):
    monkeypatch.setattr(jobs, "settings", Settings(airflow_token=TOKEN, read_token="read-token"))
    monkeypatch.setattr(service, "fetch", _fetcher(SOFR))
    auth = {"Authorization": f"Bearer {TOKEN}"}
    r = client.post("/jobs/futures/nyfed-sofr/capture?period=2026-10", headers=auth)
    assert r.status_code == 200 and r.json()["new_capture"]
    assert client.post("/jobs/futures/nope/capture", headers=auth).status_code == 404
    assert client.post("/jobs/futures/NYFED-SOFR/capture?period=2026-1", headers=auth).status_code == 400
    monkeypatch.setattr(service, "fetch", _fetcher(NO_RATES))
    r = client.post("/jobs/futures/NYFED-EFFR/capture?period=2026-10", headers=auth)
    assert r.status_code == 502 and fut.NOT_PUBLISHED in r.json()["detail"]
