"""Near-raw calendar rows (docs/phase-2.md, Part A): each source as it states itself."""

from datetime import date, time

import pytest
from sqlalchemy import func, select

from app import db
from app.calendars import near_raw, service
from app.calendars.parsed import ParseError
from app.models import CalendarDay, SourceDay, SourceYear


def _fetcher(body: bytes):
    return lambda url: (200, "text/html", body)


def _count(s, model, *where):
    return s.scalar(select(func.count()).select_from(model).where(*where))


def test_a_capture_fills_its_sources_near_raw(migrated_db, fed_html):
    with db.session() as s:
        out = service.run_capture(s, "FED", _fetcher(fed_html))["sources"]
    k8, rules = out
    assert k8["near_raw"] == {"new_years": 5, "added": 50, "changed": 0, "removed": 0}
    assert rules["near_raw"]["added"] == 382
    with db.session() as s:
        assert near_raw.years(s, "FED-K8") == [2026, 2027, 2028, 2029, 2030]
        assert len(near_raw.current_days(s, "FED-K8")) == 50
        assert len(near_raw.current_days(s, "FED-RULES")) == 382


def test_both_sources_keep_a_date_that_precedence_gives_to_one(migrated_db, sifma_fetch):
    """Good Friday 2015: the archive says early close, the PDF says something else; the
    calendar keeps the archive's (held_by_higher_source), near-raw keeps both."""
    with db.session() as s:
        service.run_capture(s, "SIFMA-US", sifma_fetch)
    gf = date(2015, 4, 3)
    with db.session() as s:
        archive = [d for d in near_raw.current_days(s, "SIFMA-US-ARCHIVE") if d.day == gf]
        pdf = [d for d in near_raw.current_days(s, "SIFMA-US-HISTORY") if d.day == gf]
        cal = s.scalars(select(CalendarDay).where(CalendarDay.day == gf, CalendarDay.valid_to.is_(None))).all()
    assert len(archive) == 1 and len(pdf) == 1 and len(cal) == 1
    assert archive[0].status == "early_close" and archive[0].close_time == time(12, 0)
    assert (cal[0].status, cal[0].close_time) == (archive[0].status, archive[0].close_time)


def test_same_content_changes_nothing(migrated_db, fed_html):
    with db.session() as s:
        service.run_capture(s, "FED", _fetcher(fed_html))
    with db.session() as s:
        out = service.run_capture(s, "FED", _fetcher(fed_html))["sources"][0]
    assert out["near_raw"] == {"new_years": 0, "added": 0, "changed": 0, "removed": 0}
    with db.session() as s:
        assert _count(s, SourceDay, SourceDay.valid_to.is_not(None)) == 0


def test_a_changed_date_keeps_history_with_capture_times(migrated_db, fed_html):
    with db.session() as s:
        service.run_capture(s, "FED", _fetcher(fed_html))
    moved = fed_html.replace(b"<td>October 12</td>", b"<td>October 19</td>")
    with db.session() as s:
        out = service.run_capture(s, "FED", _fetcher(moved))["sources"][0]
    assert out["near_raw"]["added"] == 1 and out["near_raw"]["removed"] == 1
    with db.session() as s:
        old = s.scalar(select(SourceDay).where(SourceDay.day == date(2026, 10, 12)))
        new = s.scalar(select(SourceDay).where(SourceDay.day == date(2026, 10, 19)))
        assert old.valid_to is not None and new.valid_to is None
        assert old.valid_to == new.valid_from  # both the second capture's fetch time


def test_rebuild_replays_every_capture_to_the_same_rows(migrated_db, fed_html):
    moved = fed_html.replace(b"<td>October 12</td>", b"<td>October 19</td>")
    with db.session() as s:
        service.run_capture(s, "FED", _fetcher(fed_html))
        service.run_capture(s, "FED", _fetcher(moved))

    def snapshot():
        with db.session() as s:
            return sorted(
                (r.source_id, r.day, r.status, r.close_time, r.holiday, r.capture_id, r.valid_from, r.valid_to)
                for r in s.scalars(select(SourceDay))
            ), sorted((y.source_id, y.year, y.capture_id) for y in s.scalars(select(SourceYear)))

    before = snapshot()
    with db.session() as s:
        out = service.run_near_raw_rebuild(s, "FED")
    assert snapshot() == before
    k8 = out["sources"][0]
    assert k8 == {
        "source": "FED-K8", "captures": 2, "applied": 2, "years": 5, "first_year": 2026, "last_year": 2030,
        "current_days": 50, "superseded_days": 1,
    }


def test_rebuild_fills_near_raw_for_captures_taken_before_it_existed(migrated_db, fed_html):
    with db.session() as s:
        service.run_capture(s, "FED", _fetcher(fed_html))
        s.query(SourceDay).delete()
        s.query(SourceYear).delete()
        s.commit()
    with db.session() as s:
        service.run_near_raw_rebuild(s, "FED")
        assert len(near_raw.current_days(s, "FED-K8")) == 50
        assert len(near_raw.years(s, "FED-RULES")) == 40


def test_rebuild_skips_a_capture_that_fails_to_parse(migrated_db, fed_html):
    with db.session() as s:
        service.run_capture(s, "FED", _fetcher(fed_html))
    with pytest.raises(ParseError), db.session() as s:  # a 422 for the job; the raw capture is kept
        service.run_capture(s, "FED", _fetcher(b"<html>not the K.8 page</html>"))
    with db.session() as s:
        k8 = service.run_near_raw_rebuild(s, "FED")["sources"][0]
    assert k8["captures"] == 2 and k8["applied"] == 1 and len(k8["parse_failed"]) == 1
    assert k8["current_days"] == 50


def test_a_source_without_a_parser_has_no_near_raw(migrated_db, sifma_fetch, monkeypatch):
    from dataclasses import replace

    spec = service.CALENDARS["SIFMA-US"]
    sources = tuple(replace(x, parse=None) if x.name == "SIFMA-US-HISTORY" else x for x in spec.sources)
    monkeypatch.setitem(service.CALENDARS, "SIFMA-US", replace(spec, sources=sources))
    with db.session() as s:
        service.run_capture(s, "SIFMA-US", sifma_fetch)
        out = service.run_near_raw_rebuild(s, "SIFMA-US")
        assert near_raw.current_days(s, "SIFMA-US-HISTORY") == []
    assert {"source": "SIFMA-US-HISTORY", "parsed": False, "note": service.NOT_PARSED} in out["sources"]
