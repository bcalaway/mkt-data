"""The capture → parse → apply flow against a real (SQLite) database at head."""

from dataclasses import replace
from datetime import date, time

import pytest
from sqlalchemy import func, select

from app import db
from app.calendars import service
from app.calendars.parsed import ParseError
from app.models import Calendar, CalendarDay, CalendarYear, Capture, Source, SourceCheck


def _fetcher(body: bytes):
    return lambda url: (200, "text/html", body)


def _failing(url):
    raise service.SourceFetchError(f"{url}: HTTP 503")


# Closed weekdays FED-RULES generates for 1986-2025 (tests/test_rules.py pins it too).
FED_RULES_DAYS = 382


def _count(s, model, *where):
    return s.scalar(select(func.count()).select_from(model).where(*where))


def test_first_capture_loads_every_year(migrated_db, fed_html):
    with db.session() as s:
        out = service.run_capture(s, "FED", _fetcher(fed_html))["sources"][0]
    assert out["source"] == "FED-K8" and out["new_capture"] is True
    assert out["years"] == [2026, 2027, 2028, 2029, 2030] == out["new_years"]
    assert out["added"] == out["closed_days"] == 50
    with db.session() as s:
        # FED-RULES adds 1986-2025 (repo:fed.json) alongside K.8's five years.
        assert _count(s, CalendarDay, CalendarDay.valid_to.is_(None)) == 50 + FED_RULES_DAYS
        assert _count(s, CalendarYear) == 5 + 40


def test_same_content_records_a_check_but_no_new_capture(migrated_db, fed_html):
    with db.session() as s:
        service.run_capture(s, "FED", _fetcher(fed_html))
    with db.session() as s:
        out = service.run_capture(s, "FED", _fetcher(fed_html))["sources"][0]
    assert out["new_capture"] is False and out["added"] == 0 and out["changed"] == [] == out["removed"]
    with db.session() as s:
        assert _count(s, Capture) == 2  # K.8 and the rules file, each once
        outcomes = s.scalars(select(SourceCheck.outcome).order_by(SourceCheck.id)).all()
        assert outcomes == ["new", "new", "unchanged", "unchanged"]


def test_a_changed_date_keeps_history(migrated_db, fed_html):
    with db.session() as s:
        service.run_capture(s, "FED", _fetcher(fed_html))
    # Pretend the Fed moved 2026's Columbus Day observance by a week.
    moved = fed_html.replace(b"<td>October 12</td>", b"<td>October 19</td>")
    with db.session() as s:
        out = service.run_capture(s, "FED", _fetcher(moved))["sources"][0]
    assert out["new_capture"] is True
    assert out["added"] == 1 and out["removed"] == ["2026-10-12"]
    with db.session() as s:
        old = s.scalar(select(CalendarDay).where(CalendarDay.day == date(2026, 10, 12)))
        assert old.valid_to is not None  # closed off, not deleted
        assert _count(s, CalendarDay, CalendarDay.valid_to.is_(None)) == 50 + FED_RULES_DAYS
        assert _count(s, Capture) == 3  # two K.8 versions and the rules file


def test_parse_error_keeps_the_raw_capture(migrated_db, fed_html):
    broken = fed_html.replace(b"<td>July 4**</td>", b"<td>July 4</td>")
    with db.session() as s, pytest.raises(ParseError):
        service.run_capture(s, "FED", _fetcher(broken))
    with db.session() as s:
        assert _count(s, Capture) == 2  # K.8's (kept, though it didn't parse) and the rules file
        assert _count(s, CalendarDay, CalendarDay.day >= date(2026, 1, 1)) == 0  # nothing from K.8


def test_fetch_error_is_recorded(migrated_db):
    with db.session() as s, pytest.raises(service.SourceFetchError):
        service.run_capture(s, "FED", _failing)
    with db.session() as s:
        # K.8's fetch failed; the rules file (read from the repo, not fetched) still applied.
        assert s.scalars(select(SourceCheck.outcome).order_by(SourceCheck.id)).all() == ["error", "new"]


def test_business_day(migrated_db, fed_html):
    with db.session() as s:
        service.run_capture(s, "FED", _fetcher(fed_html))
    with db.session() as s:
        assert service.business_day(s, "FED", date(2027, 7, 5))["business_day"] is False
        assert service.business_day(s, "FED", date(2026, 7, 3))["business_day"] is True
        assert service.business_day(s, "FED", date(2026, 10, 3))["status"] == "weekend"
        with pytest.raises(service.NotCovered):
            service.business_day(s, "FED", date(2031, 3, 4))
        # Older years come from FED-RULES.
        assert service.business_day(s, "FED", date(1986, 1, 20))["holiday"] == "Birthday of Martin Luther King, Jr."
        assert service.business_day(s, "FED", date(2005, 12, 26))["holiday"] == "Christmas Day (observed)"
        assert service.business_day(s, "FED", date(2004, 12, 24))["business_day"] is True  # Saturday Christmas
        assert service.business_day(s, "FED", date(2021, 6, 18))["business_day"] is True  # Juneteenth 2021
        with pytest.raises(service.NotCovered):
            service.business_day(s, "FED", date(1985, 3, 4))


def test_sifma_capture_and_early_close(migrated_db, sifma_fetch):
    with db.session() as s:
        out = service.run_capture(s, "SIFMA-US", sifma_fetch)
    page, archive, history, exceptions = out["sources"]
    assert exceptions["source"] == "SIFMA-US-EXCEPTIONS" and exceptions["years"] == []
    assert page["source"] == "SIFMA-US-HOLIDAYS" and archive["source"] == "SIFMA-US-ARCHIVE"
    assert history["source"] == "SIFMA-US-HISTORY" and history["years"] == list(range(1996, 2020))
    assert page["years"] == [2026] and page["added"] == page["closed_days"] == 19
    assert archive["years"] == list(range(2015, 2026))
    with db.session() as s:
        gf = service.business_day(s, "SIFMA-US", date(2026, 4, 3))
        assert gf == {
            "calendar": "SIFMA-US", "date": "2026-04-03", "business_day": True,
            "status": "early_close", "holiday": "Good Friday (early close)", "close_time": "12:00",
        }
        assert service.business_day(s, "SIFMA-US", date(2026, 11, 26))["business_day"] is False
        assert service.business_day(s, "SIFMA-US", date(2026, 11, 30))["status"] == "open"
        with pytest.raises(service.NotCovered):  # Jan 1, 2027 is stored, but 2027 isn't published
            service.business_day(s, "SIFMA-US", date(2027, 3, 1))


def test_sifma_archive_backfills_past_years(migrated_db, sifma_fetch):
    with db.session() as s:
        service.run_capture(s, "SIFMA-US", sifma_fetch)
    with db.session() as s:
        bd = lambda d: service.business_day(s, "SIFMA-US", d)
        assert bd(date(2021, 4, 2))["close_time"] == "12:00"  # "Early Close Only", with a trailing note
        assert bd(date(2015, 4, 3))["close_time"] == "12:00"  # "(12:00 Noon Eastern Time)"
        assert bd(date(2024, 11, 29))["close_time"] == "14:00"
        assert bd(date(2022, 6, 20))["business_day"] is False  # Juneteenth observed
        assert bd(date(2019, 6, 19))["status"] == "open"  # before Juneteenth
        with pytest.raises(service.NotCovered):
            bd(date(1995, 6, 1))
        years = s.scalars(select(CalendarYear.year).join(Calendar).where(Calendar.name == "SIFMA-US")).all()
        assert sorted(years) == list(range(1996, 2027))  # the PDF, then the archive, then the page


def test_the_page_outranks_the_archive(migrated_db, sifma_html, sifma_archive_html, sifma_history_pdf):
    # The archive also lists Dec 31, 2025 (as a full close, say): the page's early close stands.
    clash = sifma_archive_html.replace(
        b"<p>Early Close (2:00 p.m. Eastern Time): Wednesday, December 31, 2025</p>",
        b"<p>Wednesday, December 31, 2025</p>",
    )
    assert clash != sifma_archive_html
    from app.calendars import sifma

    pages = {sifma.URL: sifma_html, sifma.ARCHIVE_URL: clash, sifma.HISTORY_URL: sifma_history_pdf}
    with db.session() as s:
        out = service.run_capture(s, "SIFMA-US", lambda url: (200, "text/html", pages[url]))
    assert out["sources"][1]["held_by_higher_source"] == ["2025-12-31"]
    with db.session() as s:
        assert service.business_day(s, "SIFMA-US", date(2025, 12, 31))["status"] == "early_close"
        # The archive's later runs don't remove the page's row, and don't re-add theirs.
        out = service.run_reparse(s, "SIFMA-US")
    assert out["sources"][1]["added"] == 0 and out["sources"][1]["removed"] == []


def test_one_source_failing_does_not_stop_the_other(migrated_db, sifma_html):
    from app.calendars import sifma

    def fetch(url):
        if url == sifma.ARCHIVE_URL:
            raise service.SourceFetchError(f"{url}: HTTP 503")
        return 200, "text/html", sifma_html

    with db.session() as s, pytest.raises(service.SourceFetchError, match="SIFMA-US-ARCHIVE"):
        service.run_capture(s, "SIFMA-US", fetch)
    with db.session() as s:
        assert service.business_day(s, "SIFMA-US", date(2026, 4, 3))["status"] == "early_close"
        # The page, the PDF source (this fake answers every URL with the page) and the exceptions file.
        assert _count(s, Capture) == 3


def test_calendars_are_independent(migrated_db, fed_html, sifma_fetch):
    with db.session() as s:
        service.run_capture(s, "FED", _fetcher(fed_html))
        service.run_capture(s, "SIFMA-US", sifma_fetch)
    with db.session() as s:
        # Good Friday: the Fed is open; SIFMA recommends a noon close.
        assert service.business_day(s, "FED", date(2026, 4, 3))["status"] == "open"
        assert service.business_day(s, "SIFMA-US", date(2026, 4, 3))["status"] == "early_close"
        assert _count(s, Capture) == 6  # FED's page and rules; SIFMA's page, archive, PDF and exceptions


def test_nyse_capture_and_early_close(migrated_db, nyse_html):
    with db.session() as s:
        out = service.run_capture(s, "NYSE", _fetcher(nyse_html))["sources"][0]
    # 29 holidays over 2026-2028 (no New Year's Day in 2028) plus 5 early closes.
    assert out["years"] == [2026, 2027, 2028] and out["added"] == out["closed_days"] == 34
    with db.session() as s:
        eve = service.business_day(s, "NYSE", date(2026, 12, 24))
        assert eve == {
            "calendar": "NYSE", "date": "2026-12-24", "business_day": True,
            "status": "early_close", "holiday": "Christmas Day (early close)", "close_time": "13:00",
        }
        assert service.business_day(s, "NYSE", date(2027, 12, 24))["status"] == "closed"
        assert service.business_day(s, "NYSE", date(2027, 12, 31))["status"] == "open"
        with pytest.raises(service.NotCovered):
            service.business_day(s, "NYSE", date(2029, 1, 2))


def test_good_friday_across_the_three_calendars(migrated_db, fed_html, sifma_fetch, nyse_html):
    with db.session() as s:
        for name, fetcher in [("FED", _fetcher(fed_html)), ("SIFMA-US", sifma_fetch), ("NYSE", _fetcher(nyse_html))]:
            service.run_capture(s, name, fetcher)
    with db.session() as s:
        statuses = {n: service.business_day(s, n, date(2026, 4, 3))["status"] for n in service.CALENDARS}
        assert statuses == {"FED": "open", "SIFMA-US": "early_close", "NYSE": "closed"}
        assert _count(s, Capture) == 8  # FED 2, SIFMA-US 4, NYSE 2 (the hours page and its rules)


def test_a_source_without_a_parser_is_kept_raw(migrated_db, sifma_fetch, sifma_history_pdf, monkeypatch):
    # A new document is first captured with no parser (parse=None), as the PDF was.
    spec = service.CALENDARS["SIFMA-US"]
    raw = replace(spec.sources[2], parse=None)
    monkeypatch.setitem(service.CALENDARS, "SIFMA-US", replace(spec, sources=(*spec.sources[:2], raw, *spec.sources[3:])))
    with db.session() as s:
        out = service.run_capture(s, "SIFMA-US", sifma_fetch)["sources"][2]
    assert out == {
        "source": "SIFMA-US-HISTORY", "capture_id": out["capture_id"], "new_capture": True,
        "parsed": False, "note": service.NOT_PARSED,
    }
    with db.session() as s:
        cap = s.get(Capture, out["capture_id"])
        assert cap.body == sifma_history_pdf and cap.content_type == "application/pdf"
        assert _count(s, CalendarDay, CalendarDay.capture_id == cap.id) == 0
        # The same PDF again is a check, not a new capture; reparse skips it.
        again = service.run_capture(s, "SIFMA-US", sifma_fetch)["sources"][2]
        assert again["capture_id"] == cap.id and again["new_capture"] is False
        assert service.run_reparse(s, "SIFMA-US")["sources"][2]["parsed"] is False


def test_the_pdf_fills_older_years_and_archive_gaps(migrated_db, sifma_fetch):
    with db.session() as s:
        history = service.run_capture(s, "SIFMA-US", sifma_fetch)["sources"][2]
    # The archive outranks the PDF where they disagree: Good Friday 2015 (noon early close, not a full close).
    assert history["held_by_higher_source"] == ["2015-04-03"]
    with db.session() as s:
        bd = lambda d: service.business_day(s, "SIFMA-US", d)
        assert bd(date(2015, 4, 3))["close_time"] == "12:00"
        # Dates the archive leaves out: Presidents Day 2015 and 2016, and the Bush day of mourning.
        assert bd(date(2015, 2, 16))["business_day"] is False
        assert bd(date(2016, 2, 15))["holiday"] == "Presidents Day"
        assert bd(date(2018, 12, 5))["holiday"] == "Former President George H.W. Bush"
        assert bd(date(2012, 10, 30))["holiday"] == "Hurricane Sandy"
        assert bd(date(1999, 12, 31))["close_time"] == "13:00"
        assert bd(date(1996, 7, 5))["status"] == "early_close"


def test_sifma_exceptions_add_carter_without_covering_a_year(migrated_db, sifma_fetch):
    with db.session() as s:
        out = service.run_capture(s, "SIFMA-US", sifma_fetch)["sources"][3]
    assert out["source"] == "SIFMA-US-EXCEPTIONS" and out["added"] == 1 and out["years"] == []
    with db.session() as s:
        carter = service.business_day(s, "SIFMA-US", date(2025, 1, 9))
        assert (carter["status"], carter["close_time"]) == ("early_close", "14:00")
        cap = s.get(Capture, out["capture_id"])
        assert cap.content_type == "application/json" and b"2025-01-09" in cap.body


def test_a_missing_rules_file_is_a_fetch_error(migrated_db, fed_html, monkeypatch):
    spec = service.CALENDARS["FED"]
    gone = replace(spec.sources[1], url="repo:nope.json")
    monkeypatch.setitem(service.CALENDARS, "FED", replace(spec, sources=(spec.sources[0], gone)))
    with db.session() as s, pytest.raises(service.SourceFetchError, match="FED-RULES"):
        service.run_capture(s, "FED", _fetcher(fed_html))


def test_nyse_rules_fill_1990_to_2025(migrated_db, nyse_html):
    with db.session() as s:
        out = service.run_capture(s, "NYSE", _fetcher(nyse_html))["sources"][1]
    assert out["source"] == "NYSE-RULES" and out["years"] == list(range(1990, 2026))
    with db.session() as s:
        bd = lambda d: service.business_day(s, "NYSE", d)
        assert bd(date(2001, 9, 13))["holiday"] == "September 11 attacks"
        assert bd(date(1997, 10, 27))["close_time"] == "15:30"
        assert bd(date(2021, 12, 24))["holiday"] == "Christmas Day (observed)"
        assert bd(date(2022, 1, 3))["status"] == "open"  # Saturday New Year's: no Friday or Monday off
        with pytest.raises(service.NotCovered):
            bd(date(1989, 6, 1))


# --- Projected sources (marked `projections`; see conftest._no_projections)


def _json_source(name: str, projected: bool = False):
    """A source whose page is JSON: {"years": [...], "days": [[iso date, status, holiday, "HH:MM" or null]]}."""
    import json

    from app.calendars.parsed import Day, ParsedCalendar

    def parse(body: bytes) -> ParsedCalendar:
        data = json.loads(body)
        days = tuple(Day(date.fromisoformat(d), st, h, time.fromisoformat(t) if t else None) for d, st, h, t in data["days"])
        return ParsedCalendar(tuple(data["years"]), days)

    return service.SourceSpec(name, f"https://example.org/{name}", name, parse, projected=projected)


@pytest.mark.projections
def test_a_projection_fills_only_unpublished_years_and_gives_way_by_whole_years(migrated_db, monkeypatch):
    import json

    pages = {
        "X-PUB": {"years": [2026], "days": [["2026-01-01", "closed", "New Year's Day", None]]},
        "X-PROJ": {
            "years": [2026, 2027, 2028],
            "days": [
                ["2026-01-01", "closed", "New Year's Day", None],
                ["2026-12-25", "closed", "Christmas Day", None],
                ["2027-03-26", "closed", "Good Friday", None],
                ["2027-12-24", "closed", "Christmas Day (observed)", None],
                ["2028-01-03", "closed", "New Year's Day (observed)", None],
            ],
        },
    }
    spec = service.CalendarSpec("X", "test", "America/New_York", (_json_source("X-PUB"), _json_source("X-PROJ", True)))
    monkeypatch.setitem(service.CALENDARS, "X", spec)
    fetch = lambda url: (200, "application/json", json.dumps(pages[url.rsplit("/", 1)[1]]).encode())

    with db.session() as s:
        proj = service.run_capture(s, "X", fetch)["sources"][1]
    assert proj["years"] == [2027, 2028] and proj["added"] == 3  # 2026 is the publisher's
    with db.session() as s:
        bd = lambda d: service.business_day(s, "X", d)
        assert bd(date(2026, 12, 25)) == {"calendar": "X", "date": "2026-12-25", "business_day": True, "status": "open"}
        assert bd(date(2027, 3, 26))["projected"] is True and bd(date(2027, 3, 26))["business_day"] is False

    # The publisher adds 2027: an early close on Dec 24, and no Good Friday close.
    pages["X-PUB"] = {
        "years": [2026, 2027],
        "days": [["2026-01-01", "closed", "New Year's Day", None], ["2027-12-24", "early_close", "Christmas Eve", "13:00"]],
    }
    with db.session() as s:
        pub, proj = service.run_capture(s, "X", fetch)["sources"]
    assert pub["changed"] == ["2027-12-24"]  # overrides the projected row
    assert proj["years"] == [2028] and proj["retired_for_published_years"] == 1  # Good Friday 2027
    with db.session() as s:
        bd = lambda d: service.business_day(s, "X", d)
        assert bd(date(2027, 3, 26)) == {"calendar": "X", "date": "2027-03-26", "business_day": True, "status": "open"}
        assert bd(date(2027, 12, 24))["close_time"] == "13:00" and "projected" not in bd(date(2027, 12, 24))
        assert bd(date(2028, 1, 3))["projected"] is True
        retired = s.scalar(select(CalendarDay).where(CalendarDay.day == date(2027, 3, 26)))
        assert retired.valid_to is not None  # kept as history
    # Running again changes nothing.
    with db.session() as s:
        again = service.run_reparse(s, "X")["sources"][1]
    assert again["added"] == 0 and "retired_for_published_years" not in again


@pytest.mark.projections
def test_a_published_day_matching_the_projection_survives_the_handover(migrated_db, monkeypatch):
    """The publisher adds a year whose dates the projection already holds, word for word.

    The hub's SIFMA-US 2027 (#27, 2026-10-04): every full close that matched
    the projection exactly (Good Friday, MLK Day, Labor Day, Thanksgiving)
    stayed owned by the projection, which then retired it as the publisher's
    year, so those days read as open.
    """
    import json

    gf = ["2027-03-26", "closed", "Good Friday", None]
    pages = {
        "X-PUB": {"years": [2026], "days": [["2026-01-01", "closed", "New Year's Day", None]]},
        "X-PROJ": {"years": [2026, 2027], "days": [["2026-01-01", "closed", "New Year's Day", None], gf]},
    }
    spec = service.CalendarSpec("X", "test", "America/New_York", (_json_source("X-PUB"), _json_source("X-PROJ", True)))
    monkeypatch.setitem(service.CALENDARS, "X", spec)
    fetch = lambda url: (200, "application/json", json.dumps(pages[url.rsplit("/", 1)[1]]).encode())
    with db.session() as s:
        service.run_capture(s, "X", fetch)

    pages["X-PUB"] = {"years": [2026, 2027], "days": [["2026-01-01", "closed", "New Year's Day", None], gf]}
    for taken in (1, None):  # the handover, then a later run that must leave it alone
        with db.session() as s:
            pub, proj = service.run_capture(s, "X", fetch)["sources"]
        assert pub.get("taken_from_lower_source") == taken and pub["added"] == 0
        with db.session() as s:
            assert service.business_day(s, "X", date(2027, 3, 26)) == {
                "calendar": "X", "date": "2027-03-26", "business_day": False, "status": "closed", "holiday": "Good Friday",
            }
        assert "retired_for_published_years" not in proj
    with db.session() as s:
        rows = s.scalars(select(CalendarDay).where(CalendarDay.day == date(2027, 3, 26))).all()
        assert sum(r.valid_to is None for r in rows) == 1  # one current row, now the publisher's


@pytest.mark.projections
def test_sifma_us_runs_to_2100(migrated_db, sifma_fetch):
    with db.session() as s:
        out = service.run_capture(s, "SIFMA-US", sifma_fetch)["sources"]
    assert [x["source"] for x in out][-1] == "SIFMA-US-PROJECTED"
    assert out[-1]["years"] == list(range(2027, 2101))  # 2026 is published
    with db.session() as s:
        bd = lambda d: service.business_day(s, "SIFMA-US", d)
        assert "projected" not in bd(date(2026, 4, 3))  # the page's noon early close
        assert bd(date(2027, 3, 26)) | {"holiday": ""} == {
            "calendar": "SIFMA-US", "date": "2027-03-26", "business_day": False, "status": "closed",
            "holiday": "", "projected": True,
        }
        assert bd(date(2099, 12, 25))["projected"] is True
        assert bd(date(2025, 1, 9))["status"] == "early_close"  # Carter, from the exceptions file
        years = s.scalars(select(CalendarYear.year).join(Calendar).where(Calendar.name == "SIFMA-US")).all()
        assert sorted(years) == list(range(1996, 2101))


def test_k8_markup_changes_with_identical_text_are_not_new_captures(migrated_db, fed_html):
    with db.session() as s:
        service.run_capture(s, "FED", _fetcher(fed_html))
    # A per-request token in a script or attribute: different bytes, same visible text.
    noisy = fed_html.replace(b"<head>", b'<head><script>var nonce = "a1b2c3";</script>', 1)
    assert noisy != fed_html
    with db.session() as s:
        out = service.run_capture(s, "FED", _fetcher(noisy))["sources"][0]
    assert out["new_capture"] is False
    with db.session() as s:
        k8 = select(Source.id).where(Source.name == "FED-K8").scalar_subquery()
        assert _count(s, Capture, Capture.source_id == k8) == 1
        check = s.scalars(select(SourceCheck).where(SourceCheck.source_id == k8).order_by(SourceCheck.id.desc())).first()
        assert check.outcome == "unchanged" and check.detail.startswith("markup changed")
    # A change to the text is a new capture as usual.
    moved = fed_html.replace(b"<td>October 12</td>", b"<td>October 19</td>")
    with db.session() as s:
        assert service.run_capture(s, "FED", _fetcher(moved))["sources"][0]["new_capture"] is True


def test_other_sources_still_compare_bytes(migrated_db, nyse_html):
    with db.session() as s:
        service.run_capture(s, "NYSE", _fetcher(nyse_html))
    noisy = nyse_html.replace(b"<head>", b"<head><script>var nonce = 1;</script>", 1)
    assert noisy != nyse_html
    with db.session() as s:
        assert service.run_capture(s, "NYSE", _fetcher(noisy))["sources"][0]["new_capture"] is True
