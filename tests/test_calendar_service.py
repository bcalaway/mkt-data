"""The capture → parse → near-raw flow against a real (SQLite) database at head.

Since phase 2 (step A5) mkt-data records each source as that source states it
(near-raw); merging sources into one calendar is calendar-svc's job, and its
precedence and projection rules are tested there. These tests check each
source's capture, parse and near-raw rows, with the real-world dates each
source is known for.
"""

from dataclasses import replace
from datetime import date, time

import pytest
from sqlalchemy import func, select

from app import db
from app.calendars import near_raw, service
from app.calendars.parsed import ParseError
from app.models import Capture, Source, SourceCheck, SourceDay
from tests.conftest import FIXTURES


def _fetcher(body: bytes):
    return lambda url: (200, "text/html", body)


def _failing(url):
    raise service.SourceFetchError(f"{url}: HTTP 503")


# Closed weekdays FED-RULES generates for 1986-2025 (tests/test_rules.py pins it too).
FED_RULES_DAYS = 382


def _count(s, model, *where):
    return s.scalar(select(func.count()).select_from(model).where(*where))


def _day(s, source: str, d: date):
    """A source's current near-raw day, or None."""
    return next((x for x in near_raw.current_days(s, source) if x.day == d), None)


def test_first_capture_records_every_year(migrated_db, fed_html):
    with db.session() as s:
        out = service.run_capture(s, "FED", _fetcher(fed_html))["sources"][0]
    assert out["source"] == "FED-K8" and out["new_capture"] is True
    assert out["years"] == [2026, 2027, 2028, 2029, 2030] and out["new_years"] == 5
    assert out["added"] == out["days"] == 50
    with db.session() as s:
        assert len(near_raw.current_days(s, "FED-K8")) == 50
        assert len(near_raw.current_days(s, "FED-RULES")) == FED_RULES_DAYS
        assert len(near_raw.years(s, "FED-RULES")) == 40


def test_same_content_records_a_check_but_no_new_capture(migrated_db, fed_html):
    with db.session() as s:
        service.run_capture(s, "FED", _fetcher(fed_html))
    with db.session() as s:
        out = service.run_capture(s, "FED", _fetcher(fed_html))["sources"][0]
    assert out["new_capture"] is False and out["added"] == out["changed"] == out["removed"] == 0
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
    assert out["new_capture"] is True and out["added"] == 1 and out["removed"] == 1
    with db.session() as s:
        old = s.scalar(select(SourceDay).where(SourceDay.day == date(2026, 10, 12)))
        assert old.valid_to is not None  # closed off, not deleted
        assert _day(s, "FED-K8", date(2026, 10, 19)) is not None
        assert _count(s, Capture) == 3  # two K.8 versions and the rules file


def test_parse_error_keeps_the_raw_capture(migrated_db, fed_html):
    broken = fed_html.replace(b"<td>July 4**</td>", b"<td>July 4</td>")
    with db.session() as s, pytest.raises(ParseError):
        service.run_capture(s, "FED", _fetcher(broken))
    with db.session() as s:
        assert _count(s, Capture) == 2  # K.8's (kept, though it didn't parse) and the rules file
        assert near_raw.current_days(s, "FED-K8") == []  # nothing from K.8
        k8 = s.scalar(select(SourceCheck).join(Source).where(Source.name == "FED-K8"))
        assert k8.parse_outcome == "error"


def test_fetch_error_is_recorded(migrated_db):
    with db.session() as s, pytest.raises(service.SourceFetchError):
        service.run_capture(s, "FED", _failing)
    with db.session() as s:
        # K.8's fetch failed; the rules file (read from the repo, not fetched) still recorded.
        assert s.scalars(select(SourceCheck.outcome).order_by(SourceCheck.id)).all() == ["error", "new"]


def test_fed_k8_and_rules_dates(migrated_db, fed_html):
    with db.session() as s:
        service.run_capture(s, "FED", _fetcher(fed_html))
    with db.session() as s:
        assert _day(s, "FED-K8", date(2027, 7, 5)).status == "closed"
        assert _day(s, "FED-K8", date(2026, 7, 3)) is None  # July 4, 2026 is a Saturday: no weekday closes
        assert _day(s, "FED-RULES", date(1986, 1, 20)).holiday == "Birthday of Martin Luther King, Jr."
        assert _day(s, "FED-RULES", date(2005, 12, 26)).holiday == "Christmas Day (observed)"
        assert _day(s, "FED-RULES", date(2004, 12, 24)) is None  # Saturday Christmas
        assert _day(s, "FED-RULES", date(2021, 6, 18)) is None  # Juneteenth 2021 fell on a Saturday


def test_sifma_capture_and_early_close(migrated_db, sifma_fetch):
    with db.session() as s:
        out = service.run_capture(s, "SIFMA-US", sifma_fetch)
    page, archive, history, exceptions = out["sources"]
    assert exceptions["source"] == "SIFMA-US-EXCEPTIONS" and exceptions["years"] == []
    assert page["source"] == "SIFMA-US-HOLIDAYS" and archive["source"] == "SIFMA-US-ARCHIVE"
    assert history["source"] == "SIFMA-US-HISTORY" and history["years"] == list(range(1996, 2020))
    assert page["years"] == [2026] and page["added"] == page["days"] == 19
    assert archive["years"] == list(range(2015, 2026))
    with db.session() as s:
        gf = _day(s, "SIFMA-US-HOLIDAYS", date(2026, 4, 3))
        assert (gf.status, gf.close_time, gf.holiday) == ("early_close", time(12, 0), "Good Friday (early close)")
        assert _day(s, "SIFMA-US-HOLIDAYS", date(2026, 11, 26)).status == "closed"
        assert _day(s, "SIFMA-US-HOLIDAYS", date(2027, 1, 1)) is not None  # stored, though 2027 isn't covered
        assert 2027 not in near_raw.years(s, "SIFMA-US-HOLIDAYS")


def test_sifma_archive_dates(migrated_db, sifma_fetch):
    with db.session() as s:
        service.run_capture(s, "SIFMA-US", sifma_fetch)
    with db.session() as s:
        d = lambda x: _day(s, "SIFMA-US-ARCHIVE", x)
        assert d(date(2021, 4, 2)).close_time == time(12, 0)  # "Early Close Only", with a trailing note
        assert d(date(2015, 4, 3)).close_time == time(12, 0)  # "(12:00 Noon Eastern Time)"
        assert d(date(2024, 11, 29)).close_time == time(14, 0)
        assert d(date(2022, 6, 20)).status == "closed"  # Juneteenth observed
        assert d(date(2019, 6, 19)) is None  # before Juneteenth


def test_two_sources_listing_the_same_date_both_keep_it(migrated_db, sifma_fetch):
    """Good Friday 2015: the archive's noon early close and the PDF's version are both near-raw.

    Which one the calendar uses is calendar-svc's call (the archive outranks the PDF).
    """
    with db.session() as s:
        service.run_capture(s, "SIFMA-US", sifma_fetch)
    with db.session() as s:
        assert _day(s, "SIFMA-US-ARCHIVE", date(2015, 4, 3)).close_time == time(12, 0)
        assert _day(s, "SIFMA-US-HISTORY", date(2015, 4, 3)) is not None


def test_one_source_failing_does_not_stop_the_other(migrated_db, sifma_html):
    from app.calendars import sifma

    def fetch(url):
        if url == sifma.ARCHIVE_URL:
            raise service.SourceFetchError(f"{url}: HTTP 503")
        return 200, "text/html", sifma_html

    with db.session() as s, pytest.raises(service.SourceFetchError, match="SIFMA-US-ARCHIVE"):
        service.run_capture(s, "SIFMA-US", fetch)
    with db.session() as s:
        assert _day(s, "SIFMA-US-HOLIDAYS", date(2026, 4, 3)).status == "early_close"
        # The page, the PDF source (this fake answers every URL with the page) and the exceptions file.
        assert _count(s, Capture) == 3


def test_nyse_capture_and_early_close(migrated_db, nyse_html):
    with db.session() as s:
        out = service.run_capture(s, "NYSE", _fetcher(nyse_html))["sources"][0]
    # 29 holidays over 2026-2028 (no New Year's Day in 2028) plus 5 early closes.
    assert out["years"] == [2026, 2027, 2028] and out["added"] == out["days"] == 34
    with db.session() as s:
        eve = _day(s, "NYSE-HOURS", date(2026, 12, 24))
        assert (eve.status, eve.close_time, eve.holiday) == ("early_close", time(13, 0), "Christmas Day (early close)")
        assert _day(s, "NYSE-HOURS", date(2027, 12, 24)).status == "closed"
        assert _day(s, "NYSE-HOURS", date(2027, 12, 31)) is None


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
        assert _count(s, SourceDay, SourceDay.capture_id == cap.id) == 0
        # The same PDF again is a check, not a new capture; reparse skips it.
        again = service.run_capture(s, "SIFMA-US", sifma_fetch)["sources"][2]
        assert again["capture_id"] == cap.id and again["new_capture"] is False
        assert service.run_reparse(s, "SIFMA-US")["sources"][2]["parsed"] is False


def test_the_pdf_dates(migrated_db, sifma_fetch):
    with db.session() as s:
        service.run_capture(s, "SIFMA-US", sifma_fetch)
    with db.session() as s:
        d = lambda x: _day(s, "SIFMA-US-HISTORY", x)
        # Dates the archive leaves out: Presidents Day 2015 and 2016, and the Bush day of mourning.
        assert d(date(2015, 2, 16)).status == "closed"
        assert d(date(2016, 2, 15)).holiday == "Presidents Day"
        assert d(date(2018, 12, 5)).holiday == "Former President George H.W. Bush"
        assert d(date(2012, 10, 30)).holiday == "Hurricane Sandy"
        assert d(date(1999, 12, 31)).close_time == time(13, 0)
        assert d(date(1996, 7, 5)).status == "early_close"


def test_sifma_exceptions_add_carter_without_covering_a_year(migrated_db, sifma_fetch):
    with db.session() as s:
        out = service.run_capture(s, "SIFMA-US", sifma_fetch)["sources"][3]
    assert out["source"] == "SIFMA-US-EXCEPTIONS" and out["added"] == 1 and out["years"] == []
    with db.session() as s:
        carter = _day(s, "SIFMA-US-EXCEPTIONS", date(2025, 1, 9))
        assert (carter.status, carter.close_time) == ("early_close", time(14, 0))
        cap = s.get(Capture, out["capture_id"])
        assert cap.content_type == "application/json" and b"2025-01-09" in cap.body


def test_a_missing_rules_file_is_a_fetch_error(migrated_db, fed_html, monkeypatch):
    spec = service.CALENDARS["FED"]
    gone = replace(spec.sources[1], url="repo:nope.json")
    monkeypatch.setitem(service.CALENDARS, "FED", replace(spec, sources=(spec.sources[0], gone)))
    with db.session() as s, pytest.raises(service.SourceFetchError, match="FED-RULES"):
        service.run_capture(s, "FED", _fetcher(fed_html))


def test_nyse_rules_cover_1990_to_2025(migrated_db, nyse_html):
    with db.session() as s:
        out = service.run_capture(s, "NYSE", _fetcher(nyse_html))["sources"][1]
    assert out["source"] == "NYSE-RULES" and out["years"] == list(range(1990, 2026))
    with db.session() as s:
        d = lambda x: _day(s, "NYSE-RULES", x)
        assert d(date(2001, 9, 13)).holiday == "September 11 attacks"
        assert d(date(1997, 10, 27)).close_time == time(15, 30)
        assert d(date(2021, 12, 24)).holiday == "Christmas Day (observed)"
        assert d(date(2022, 1, 3)) is None  # Saturday New Year's: no Friday or Monday off


@pytest.mark.projections
def test_a_projection_records_every_year_it_generates(migrated_db, sifma_fetch):
    """In near-raw a projection keeps all its years to 2100, even ones a publisher covers.

    calendar-svc fills only uncovered years with it.
    """
    with db.session() as s:
        out = service.run_capture(s, "SIFMA-US", sifma_fetch)["sources"]
    assert out[-1]["source"] == "SIFMA-US-PROJECTED"
    with db.session() as s:
        years = near_raw.years(s, "SIFMA-US-PROJECTED")
        assert years[-1] == 2100 and 2026 in years
        assert _day(s, "SIFMA-US-PROJECTED", date(2099, 12, 25)).status == "closed"


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


@pytest.mark.history_documents
def test_history_documents_are_recorded(migrated_db, fed_html, nyse_html):
    """The NY Fed circulars and NYSE's holiday history: parsed and recorded as their own sources."""
    from app.calendars import fed, nyse
    from tests.test_nyfed_parser import CAPTURES

    pages = {fed.URL: fed_html, nyse.URL: nyse_html,
             nyse.HISTORY_URL: (FIXTURES / "nyse_history_capture17.pdf").read_bytes()}
    for year, url in fed.NYFED_CIRCULARS.items():
        pages[url] = (FIXTURES / f"nyfed_circular_{year}_capture{CAPTURES[year][0]}.html").read_bytes()
    fetch = lambda url: (200, "text/html", pages[url])
    with db.session() as s:
        fed_out = service.run_capture(s, "FED", fetch)["sources"]
        nyse_out = service.run_capture(s, "NYSE", fetch)["sources"]
    assert [x["source"] for x in fed_out] == ["FED-K8", *(f"FED-NYFED-{y}" for y in range(2009, 2002, -1)), "FED-RULES"]
    assert [x["source"] for x in nyse_out] == ["NYSE-HOURS", "NYSE-HISTORY", "NYSE-RULES"]
    circulars = {x["source"]: x for x in fed_out[1:8]}
    assert circulars["FED-NYFED-2005"]["years"] == [2005] and circulars["FED-NYFED-2005"]["days"] == 9
    assert nyse_out[1]["years"] == [] and nyse_out[1]["days"] == 55
    with db.session() as s:
        assert _day(s, "FED-NYFED-2005", date(2005, 12, 26)).holiday == "Christmas Day (observed)"
        halt = _day(s, "NYSE-HISTORY", date(2005, 6, 1))
        assert (halt.status, halt.close_time, halt.holiday) == ("early_close", time(15, 56), "Systems halt (early close)")
        assert _day(s, "NYSE-HISTORY", date(2001, 9, 11)).status == "closed"


@pytest.mark.history_documents
def test_nyfed_circular_markup_changes_are_not_new_captures(migrated_db, fed_html):
    """The NY Fed's pages change markup on every fetch (captures #15 and #23, 2026-10-04)."""
    from app.calendars import fed
    from tests.test_nyfed_parser import CAPTURES

    pages = {fed.URL: fed_html}
    for year, url in fed.NYFED_CIRCULARS.items():
        pages[url] = (FIXTURES / f"nyfed_circular_{year}_capture{CAPTURES[year][0]}.html").read_bytes()
    with db.session() as s:
        service.run_capture(s, "FED", lambda url: (200, "text/html", pages[url]))
    url09 = fed.NYFED_CIRCULARS[2009]
    pages[url09] = pages[url09].replace(b"<head>", b'<head><script>var nonce = "a1b2c3";</script>', 1)
    with db.session() as s:
        out = {x["source"]: x for x in service.run_capture(s, "FED", lambda url: (200, "text/html", pages[url]))["sources"]}
    assert out["FED-NYFED-2009"]["new_capture"] is False
    pages[url09] = pages[url09].replace(b"Circular No. 11980", b"Circular No. 11981")
    with db.session() as s:
        out = {x["source"]: x for x in service.run_capture(s, "FED", lambda url: (200, "text/html", pages[url]))["sources"]}
    assert out["FED-NYFED-2009"]["new_capture"] is True  # a text change is still a new capture
