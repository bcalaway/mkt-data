"""GET /metrics: the data-quality gauges the platform's Grafana alerts use."""

import re

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


def test_no_database_is_reported_not_raised(monkeypatch):
    monkeypatch.setattr(db, "settings", Settings(database_url=None, postgres_password=None))
    db._engine.cache_clear()
    try:
        assert _scrape() == {"mkt_data_db_up": 0}
    finally:
        db._engine.cache_clear()


def test_fed_after_a_capture(migrated_db, fed_html):
    with db.session() as s:
        service.run_capture(s, "FED", _fetcher(fed_html))
    m = _scrape()
    assert m["mkt_data_db_up"] == 1
    assert m['mkt_data_source_parse_ok{calendar="FED",source="FED-K8",kind="published"}'] == 1
    assert m['mkt_data_source_parse_ok{calendar="FED",source="FED-RULES",kind="rules"}'] == 1
    assert m['mkt_data_source_captures{calendar="FED",source="FED-K8",kind="published"}'] == 1
    assert m['mkt_data_source_capture_bytes{calendar="FED",source="FED-K8",kind="published"}'] == len(fed_html)
    # The calendars' own gauges come from calendar-svc since phase 2, A5.
    assert not [k for k in m if k.startswith("mkt_data_calendar_")]
    ts = m['mkt_data_source_last_success_timestamp_seconds{calendar="FED",source="FED-K8",kind="published"}']
    assert abs(ts - __import__("time").time()) < 300


def test_a_parse_failure_reads_0_until_a_reparse_works(migrated_db, fed_html, monkeypatch):
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


def test_label_values_are_escaped():
    out = metrics._Out()
    out.metric("m", "gauge", "h", [({"a": 'x"y\\z'}, 1.5)])
    assert re.search(r'^m\{a="x\\"y\\\\z"\} 1\.5$', out.text(), re.MULTILINE)
