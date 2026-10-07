"""Every source with how its captures are going (app/source_status.py), for the Sources screen."""

from datetime import UTC, datetime, timedelta

import pytest

from app import db, source_status
from app.models import Capture, Source, SourceCheck

NOW = datetime(2026, 10, 7, 20, 0, tzinfo=UTC)


def _source(s, name):
    src = Source(name=name, url=f"https://example.test/{name}", description=f"{name} test")
    s.add(src)
    s.flush()
    return src.id


def _capture(s, sid, at, period=None, size=100):
    c = Capture(source_id=sid, fetched_at=at, http_status=200, content_type="text/html", sha256=f"{at}{period}",
                size_bytes=size, body=b"x", period=period)
    s.add(c)
    s.flush()
    return c.id


def _check(s, sid, at, outcome, capture_id=None, parse="ok", detail=None, parse_detail=None, period=None):
    s.add(SourceCheck(source_id=sid, checked_at=at, outcome=outcome, capture_id=capture_id, detail=detail,
                      parse_outcome=parse, parse_detail=parse_detail, period=period))


def _load(s):
    fed = _source(s, "FED-K8")
    c = _capture(s, fed, NOW - timedelta(days=30), size=5000)
    _check(s, fed, NOW - timedelta(days=30), "new", c)
    _check(s, fed, NOW - timedelta(days=1), "unchanged", c)
    prices = _source(s, "TD-PRICES")
    for day, at in (("2025-12-31", NOW - timedelta(days=9)), ("2026-10-05", NOW - timedelta(days=2)),
                    ("2026-10-06", NOW - timedelta(days=1))):
        cap = _capture(s, prices, at, day, size=110_000)
        _check(s, prices, at, "new", cap, period=day)
    _check(s, prices, NOW - timedelta(hours=1), "error", parse=None, detail="HTTP 503 from FedInvest",
           period="2026-10-07")
    s.commit()


def test_the_catalog_covers_every_source_once():
    entries = source_status.catalog()
    names = [e.name for e in entries]
    assert len(names) == len(set(names))
    by = {e.name: e for e in entries}
    assert by["FED-K8"].group == "calendars" and by["FED-K8"].period_kind == ""
    assert (by["UST-PAR"].group, by["UST-PAR"].period_kind) == ("rates", "month")
    assert (by["TD-PRICES"].group, by["TD-PRICES"].period_kind, by["TD-PRICES"].calendar) == (
        "securities", "day", "SIFMA-US")


def test_list(migrated_db):
    with db.session() as s:
        _load(s)
        rows = {r["name"]: r for r in source_status.list_sources(s, NOW)}
    fed, prices, par = rows["FED-K8"], rows["TD-PRICES"], rows["UST-PAR"]
    assert (fed["captures"], fed["capture_bytes"], fed["last_outcome"], fed["checks_7d"], fed["errors_7d"]) == (
        1, 5000, "unchanged", 1, 0)
    assert fed["periods"] == 0 and fed["first_period"] == "" and fed["last_error"] == ""
    assert prices["last_outcome"] == "error" and prices["last_error"] == "HTTP 503 from FedInvest"
    assert prices["last_success_at"] == (NOW - timedelta(days=1)).isoformat()
    assert (prices["checks_7d"], prices["errors_7d"]) == (3, 1)
    assert (prices["periods"], prices["first_period"], prices["last_period"]) == (3, "2025-12-31", "2026-10-06")
    assert par["captures"] == 0 and par["latest_capture_id"] == 0 and par["last_check_at"] == ""  # never captured
    assert par["url"].startswith("https://home.treasury.gov/")  # the template from its spec


def test_get(migrated_db):
    with db.session() as s:
        _load(s)
        d = source_status.get_source(s, "td-prices", checks=2, now=NOW)
        with pytest.raises(source_status.UnknownSource):
            source_status.get_source(s, "NOPE")
        never = source_status.get_source(s, "UST-PAR", now=NOW)
    assert [c["outcome"] for c in d["checks"]] == ["error", "new"]
    assert d["checks"][0]["capture_id"] == 0 and d["checks"][0]["period"] == "2026-10-07"
    assert d["years"] == [{"year": "2025", "periods": 1, "captures": 1, "capture_bytes": 110_000},
                          {"year": "2026", "periods": 2, "captures": 2, "capture_bytes": 220_000}]
    assert never["checks"] == [] and never["years"] == []
