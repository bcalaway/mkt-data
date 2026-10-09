"""Every source with how its captures are going (app/source_status.py), for the Sources screen."""

import json
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


def test_every_source_says_what_it_gives_and_who_reads_it():
    for e in source_status.catalog():
        text = source_status.pulls_for(e)
        assert text and any(svc in text for svc in ("calendar-svc", "quote-svc", "secmaster-svc", "cross-check")), e.name
    by = {e.name: e for e in source_status.catalog()}
    assert "precedence 1 of" in source_status.pulls_for(by["FED-K8"])
    # The tests' calendars leave out the rules files (tests/conftest.py), so a projection is made up here.
    proj = source_status.Entry("SIFMA-US-PROJECTED", "calendars", "SIFMA-US", "projected", "", by["FED-K8"].spec)
    assert "fills only years" in source_status.pulls_for(proj)


def test_schedules_match_the_dags():
    from pathlib import Path

    dags = "\n".join(p.read_text() for p in (Path(__file__).resolve().parents[1] / "dags").glob("*.py"))
    for e in source_status.catalog():
        sched = source_status.schedule_for(e)
        assert f'"{sched.dag}"' in dags, (e.name, sched.dag)
        assert f'"{sched.cron}"' in dags, (e.name, sched.cron)


def test_late_against_the_schedule(migrated_db):
    with db.session() as s:
        _load(s)
        rows = {r["name"]: r for r in source_status.list_sources(s, NOW)}
        later = {r["name"]: r for r in source_status.list_sources(s, NOW + timedelta(days=5))}
    # TD-PRICES last worked a day before NOW: on time; five days on (six since), past its 120 hours.
    assert not rows["TD-PRICES"]["late"] and later["TD-PRICES"]["late"]
    assert rows["TD-PRICES"]["dag"] == "mkt_data__treasury_securities_capture" and rows["TD-PRICES"]["late_after_hours"] == 120
    # FED-K8 last worked a day before NOW and is weekly: still on time five days on.
    assert not later["FED-K8"]["late"] and later["FED-K8"]["late_after_hours"] == 192
    assert not rows["UST-PAR"]["late"]  # never fetched: not late, never captured (the status says so)


def test_capture_text(migrated_db):
    with db.session() as s:
        sid = _source(s, "BLS-CPI")
        body = json.dumps({"status": "REQUEST_SUCCEEDED", "Results": {"series": [{"data": [
            {"year": "2026", "period": f"M{m:02d}", "value": str(320 + m)} for m in range(1, 9)]}]}}).encode()
        c = Capture(source_id=sid, fetched_at=NOW, http_status=200, content_type="application/json", sha256="a",
                    size_bytes=len(body), body=body, period="2026")
        s.add(c)
        pdf = Capture(source_id=sid, fetched_at=NOW, http_status=200, content_type="application/pdf", sha256="b",
                      size_bytes=4, body=b"%PDF", period="2025")
        s.add(pdf)
        s.commit()
        whole = source_status.capture_text(s, c.id, limit=5)
        found = source_status.capture_text(s, c.id, contains="m03", context=1)
        page2 = source_status.capture_text(s, c.id, offset=5, limit=5)
        with pytest.raises(source_status.UnknownCapture):
            source_status.capture_text(s, 999)
        from app.capture_text import NoTextView

        with pytest.raises(NoTextView):
            source_status.capture_text(s, pdf.id)
    assert whole["view"] == "json" and whole["matches"] == -1 and len(whole["lines"]) == 5 and whole["lines"][0]["n"] == 1
    assert whole["shown_of"] == whole["lines_total"] and whole["period"] == "2026" and whole["source"] == "BLS-CPI"
    assert found["matches"] == 1 and any('"M03"' in x["text"] for x in found["lines"]) and len(found["lines"]) == 3
    assert page2["offset"] == 5 and page2["lines"][0]["n"] == 6


def test_the_late_threshold_is_a_metric(migrated_db):
    from fastapi.testclient import TestClient

    from app.main import app

    with db.session() as s:
        _load(s)
    text = TestClient(app).get("/metrics").text
    assert 'mkt_data_source_late_after_seconds{calendar="SIFMA-US",source="TD-PRICES",kind="published"} 432000' in text
    assert 'mkt_data_source_late_after_seconds{calendar="FED",source="FED-K8",kind="published"} 691200' in text


def test_only_unfixed_errors_count(migrated_db):
    """Bill, 2026-10-09: the Sources screen shows only errors no later check has fixed."""
    with db.session() as s:
        _load(s)
        h10 = _source(s, "FRB-H10")
        week = NOW - timedelta(days=2)
        # A backfill that failed for June, then a re-run that fetched it: fixed.
        _check(s, h10, week, "error", parse=None, detail="empty response, 3 tries", period="2024-06")
        cap = _capture(s, h10, week + timedelta(hours=1), "2024-06")
        _check(s, h10, week + timedelta(hours=1), "new", cap, period="2024-06")
        # Another month that failed and hasn't been fetched since: not fixed, though other months worked later.
        _check(s, h10, week, "error", parse=None, detail="empty response, 3 tries", period="2023-06")
        cap = _capture(s, h10, week + timedelta(hours=2), "2023-07")
        _check(s, h10, week + timedelta(hours=2), "new", cap, period="2023-07")
        # A month not published yet is expected, not an error.
        _check(s, h10, week, "error", parse=None, detail="NOT_PUBLISHED: no rates for these dates yet",
               period="2026-11")
        # A parse error a later reparse got through: fixed.
        jp = _source(s, "JP-CAO")
        cap = _capture(s, jp, week)
        _check(s, jp, week, "new", cap, parse="error", parse_detail="1955 has 9 national holidays")
        _check(s, jp, week + timedelta(hours=1), "reparse", cap, parse="ok")
        s.commit()
        rows = {r["name"]: r for r in source_status.list_sources(s, NOW)}
    assert (rows["FRB-H10"]["checks_7d"], rows["FRB-H10"]["errors_7d"]) == (5, 1)
    assert rows["JP-CAO"]["errors_7d"] == 0
    assert rows["TD-PRICES"]["errors_7d"] == 1  # the latest check failed: nothing has fixed it
