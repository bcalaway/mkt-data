"""GET /metrics: the data-quality gauges the platform's Grafana alerts use."""

import re
from datetime import date

import pytest
from fastapi.testclient import TestClient

from app import db, metrics
from app.calendars import service
from app.calendars.parsed import ParseError
from app.config import Settings
from app.main import app

client = TestClient(app)


def _scrape() -> dict[str, float]:
    r = client.get("/metrics")
    assert r.status_code == 200 and r.headers["content-type"].startswith("text/plain")
    samples = {}
    for line in r.text.splitlines():
        if line and not line.startswith("#"):
            key, value = line.rsplit(" ", 1)
            samples[key] = float(value)
    return samples


def _fetcher(body):
    return lambda url: (200, "text/html", body)


@pytest.fixture
def today(monkeypatch):
    def set_today(d: date):
        monkeypatch.setattr(metrics, "_today", lambda: d)

    set_today(date(2026, 10, 4))
    return set_today


def test_no_database_is_reported_not_raised(monkeypatch):
    monkeypatch.setattr(db, "settings", Settings(database_url=None, postgres_password=None))
    db._engine.cache_clear()
    try:
        assert _scrape() == {"mkt_data_db_up": 0}
    finally:
        db._engine.cache_clear()


def test_fed_after_a_capture(migrated_db, fed_html, today):
    with db.session() as s:
        service.run_capture(s, "FED", _fetcher(fed_html))
    m = _scrape()
    assert m["mkt_data_db_up"] == 1
    assert m['mkt_data_source_parse_ok{calendar="FED",source="FED-K8",kind="published"}'] == 1
    assert m['mkt_data_source_parse_ok{calendar="FED",source="FED-RULES",kind="rules"}'] == 1
    assert m['mkt_data_source_captures{calendar="FED",source="FED-K8",kind="published"}'] == 1
    assert m['mkt_data_source_capture_bytes{calendar="FED",source="FED-K8",kind="published"}'] == len(fed_html)
    assert m['mkt_data_calendar_years{calendar="FED",kind="published"}'] == 5
    assert m['mkt_data_calendar_years{calendar="FED",kind="rules"}'] == 40
    assert m['mkt_data_calendar_first_year{calendar="FED",kind="rules"}'] == 1986
    assert m['mkt_data_calendar_last_year{calendar="FED",kind="published"}'] == 2030
    assert m['mkt_data_calendar_next_year_published{calendar="FED",year="2027"}'] == 1
    assert m['mkt_data_calendar_next_year_overdue{calendar="FED",year="2027"}'] == 0
    ts = m['mkt_data_source_last_success_timestamp_seconds{calendar="FED",source="FED-K8",kind="published"}']
    assert abs(ts - __import__("time").time()) < 300


def test_a_parse_failure_reads_0_until_a_reparse_works(migrated_db, fed_html, today, monkeypatch):
    broken = fed_html.replace(b"<td>July 4**</td>", b"<td>July 4</td>")
    with db.session() as s, pytest.raises(ParseError):
        service.run_capture(s, "FED", _fetcher(broken))
    assert _scrape()['mkt_data_source_parse_ok{calendar="FED",source="FED-K8",kind="published"}'] == 0
    # A parser fix, then a reparse of the same capture.
    good = service.CALENDARS["FED"].sources[0].parse(fed_html)
    spec = service.CALENDARS["FED"]
    fixed = __import__("dataclasses").replace(spec.sources[0], parse=lambda body: good)
    monkeypatch.setitem(service.CALENDARS, "FED", __import__("dataclasses").replace(spec, sources=(fixed, *spec.sources[1:])))
    with db.session() as s:
        service.run_reparse(s, "FED")
    assert _scrape()['mkt_data_source_parse_ok{calendar="FED",source="FED-K8",kind="published"}'] == 1


def test_sifma_next_year_is_overdue_only_after_mid_december(migrated_db, sifma_fetch, today):
    with db.session() as s:
        service.run_capture(s, "SIFMA-US", sifma_fetch)
    key = 'mkt_data_calendar_next_year_overdue{calendar="SIFMA-US",year="2027"}'
    assert _scrape()['mkt_data_calendar_next_year_published{calendar="SIFMA-US",year="2027"}'] == 0
    assert _scrape()[key] == 0  # October: not due yet
    today(date(2026, 12, 20))
    assert _scrape()[key] == 1


@pytest.mark.projections
def test_projections_dont_count_as_published(migrated_db, sifma_fetch, today):
    with db.session() as s:
        service.run_capture(s, "SIFMA-US", sifma_fetch)
    today(date(2026, 12, 21))
    m = _scrape()
    assert m['mkt_data_calendar_years{calendar="SIFMA-US",kind="projected"}'] == 74  # 2027-2100
    assert m['mkt_data_calendar_next_year_overdue{calendar="SIFMA-US",year="2027"}'] == 1


def test_label_values_are_escaped():
    out = metrics._Out()
    out.metric("m", "gauge", "h", [({"a": 'x"y\\z'}, 1.5)])
    assert re.search(r'^m\{a="x\\"y\\\\z"\} 1\.5$', out.text(), re.MULTILINE)


def test_upcoming_closes_and_early_closes(migrated_db, nyse_html, today):
    with db.session() as s:
        service.run_capture(s, "NYSE", _fetcher(nyse_html))
    m = _scrape()
    up = {k: v for k, v in m.items() if k.startswith('mkt_data_calendar_upcoming_day{calendar="NYSE"')}
    thanksgiving = ('mkt_data_calendar_upcoming_day{calendar="NYSE",date="2026-11-26",weekday="Thu",'
                    'holiday="Thanksgiving Day",status="closed",close_time="",projected="no"}')
    assert up[thanksgiving] == 53
    early = [k for k in up if 'date="2026-11-27"' in k]
    assert len(early) == 1 and 'status="early_close"' in early[0] and 'close_time="13:00"' in early[0]
    days = sorted(up.values())
    assert days[0] >= 0 and days[-1] <= metrics.UPCOMING_DAYS  # nothing past or beyond the window
    assert m['mkt_data_calendar_gap_years{calendar="NYSE"}'] == 0


def test_a_coverage_gap_is_reported_by_year(migrated_db, monkeypatch, today):
    import json

    from tests.test_calendar_service import _json_source

    page = {"years": [2020, 2023], "days": [["2020-01-01", "closed", "New Year's Day", None]]}
    spec = service.CalendarSpec("X", "test", "America/New_York", (_json_source("X-PUB"),))
    monkeypatch.setattr(service, "CALENDARS", {"X": spec})
    with db.session() as s:
        service.run_capture(s, "X", lambda url: (200, "application/json", json.dumps(page).encode()))
    m = _scrape()
    assert m['mkt_data_calendar_gap_years{calendar="X"}'] == 2
    assert m['mkt_data_calendar_gap_year{calendar="X",year="2021"}'] == 1
    assert m['mkt_data_calendar_gap_year{calendar="X",year="2022"}'] == 1
