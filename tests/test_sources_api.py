"""Near-raw calendar data as other services read it (app/calendars/sources_api.py)."""

import pytest

from app import db
from app.calendars import service, sources_api


def _fetcher(body: bytes):
    return lambda url: (200, "text/html", body)


def test_list_sources_before_anything_is_captured(migrated_db):
    with db.session() as s:
        rows = sources_api.list_sources(s)
    assert [r["name"] for r in rows] == [x.name for c in service.CALENDARS.values() for x in c.sources]
    k8 = rows[0]
    assert (k8["calendar"], k8["parsed"], k8["latest_capture_id"], k8["latest_applied_capture_id"]) == (
        "FED", True, 0, 0
    )


def test_list_sources_after_a_capture(migrated_db, fed_html):
    with db.session() as s:
        service.run_capture(s, "FED", _fetcher(fed_html))
        rows = {r["name"]: r for r in sources_api.list_sources(s)}
    k8 = rows["FED-K8"]
    assert k8["latest_capture_id"] > 0 and k8["latest_applied_capture_id"] == k8["latest_capture_id"]
    assert k8["latest_capture_at"]
    assert rows["NYSE-HOURS"]["latest_capture_id"] == 0


def test_source_rows_current_and_superseded(migrated_db, fed_html):
    moved = fed_html.replace(b"<td>October 12</td>", b"<td>October 19</td>")
    with db.session() as s:
        service.run_capture(s, "FED", _fetcher(fed_html))
        service.run_capture(s, "FED", _fetcher(moved))
    with db.session() as s:
        current = sources_api.source_rows(s, "FED-K8")
        everything = sources_api.source_rows(s, "FED-K8", include_superseded=True)
    assert [y["year"] for y in current["years"]] == [2026, 2027, 2028, 2029, 2030]
    assert len(current["days"]) == 50 and len(everything["days"]) == 51
    assert all(d["valid_to"] == "" for d in current["days"])
    old = [d for d in everything["days"] if d["day"] == "2026-10-12"]
    assert len(old) == 1 and old[0]["valid_to"] and old[0]["status"] == "closed" and old[0]["close_time"] == ""
    assert current["source"]["latest_applied_capture_id"] == current["source"]["latest_capture_id"]


def test_early_close_time_is_hh_mm(migrated_db, sifma_fetch):
    with db.session() as s:
        service.run_capture(s, "SIFMA-US", sifma_fetch)
        days = sources_api.source_rows(s, "SIFMA-US-HOLIDAYS")["days"]
    gf = [d for d in days if d["day"] == "2026-04-03"]
    assert gf and gf[0]["status"] == "early_close" and gf[0]["close_time"] == "12:00"


def test_unknown_source(migrated_db):
    with db.session() as s, pytest.raises(sources_api.UnknownSource):
        sources_api.source_rows(s, "NOPE")


def test_a_known_source_not_captured_yet_has_no_rows(migrated_db):
    with db.session() as s:
        out = sources_api.source_rows(s, "NYSE-HOURS")
    assert out["years"] == [] == out["days"] and out["source"]["calendar"] == "NYSE"
