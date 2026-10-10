"""The SPGMI RFR swap curves (app/swaps/): parser, fetch, capture and job; and ISDA's NYM and TYO calendars.

The curve files here are synthetic, laid out as the SPGMI Interest Rate Curve XML Specification (RFRs), v1.3,
section 4 shows (the spec is confidential, so its sample isn't copied). Replace with a real capture's bytes
(capture-export.yml) once the hub has one.
"""

import io
import zipfile
from datetime import date, datetime
from decimal import Decimal

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import func, select

from app import config, db, jobs, source_status
from app.calendars import isda, service
from app.calendars.parsed import ParseError
from app.config import Settings
from app.main import app
from app.models import Capture, Observation, Record, SourceCheck
from app.rates import api as obs_api
from app.securities import api as rec_api
from app.securities import sources as sec
from app.swaps import parsers as p
from app.swaps import sources as sw

client = TestClient(app)
TOKEN = "test-token"
EMAIL = "someone@example.com"
NOW = datetime(2026, 10, 9, 18, 15, tzinfo=sec.EASTERN)

POINTS = [("1M", "2026-11-13", "0.039012"), ("3M", "2027-01-13", "0.038544"), ("1Y", "2027-10-13", "0.036101"),
          ("2Y", "2028-10-13", "0.034877"), ("10Y", "2036-10-14", "0.036912"), ("30Y", "2056-10-13", "0.039004")]


def curve_xml(ccy="USD", effective="2026-10-12", snap="2026-10-09T16:00:00", points=POINTS, calendar="NYM",
              root="IHSM") -> bytes:
    cps = "".join(f"<curvepoint><tenor>{t}</tenor><maturitydate>{m}</maturitydate><parrate>{r}</parrate></curvepoint>"
                  for t, m, r in points)
    return (f"<?xml version='1.0' encoding='UTF-8'?><{root} xmlns:xsi=\"http://www.w3.org/2001/XMLSchema-instance\">"
            f"<interestRateCurve><effectiveasof>{effective}</effectiveasof><currency>{ccy}</currency>"
            f"<baddayconvention>M</baddayconvention><ois>"
            f"<fixeddaycountconvention>ACT/360</fixeddaycountconvention>"
            f"<floatingdaycountconvention>ACT/360</floatingdaycountconvention>"
            f"<fixedpaymentfrequency>1Y</fixedpaymentfrequency><floatingpaymentfrequency>1Y</floatingpaymentfrequency>"
            f"<snaptime>{snap}</snaptime><spotdate>2026-10-14</spotdate>"
            f"<calendars><calendar>{calendar}</calendar></calendars>{cps}</ois></interestRateCurve></{root}>").encode()


DISCLAIMER = "ISDA Standard Rate Curves Disclaimer.txt"  # beside the XML in every real file (2026-10-10)


def zipped(xml: bytes, name="InterestRates_USD_20261009.xml", when=(2026, 10, 9, 16, 50, 0), extra=(DISCLAIMER,)) -> bytes:
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as z:
        z.writestr(zipfile.ZipInfo(name, when), xml)
        for other in extra:
            z.writestr(zipfile.ZipInfo(other, when), b"disclaimer text")
    return buf.getvalue()


# --- the parser -------------------------------------------------------------------------------------------------


def test_parse_a_curve_file():
    obs, recs = p.parse_curve(zipped(curve_xml()), "USD")
    # Published Friday 2026-10-09 for trade date Monday 2026-10-12: dated the Friday.
    assert {o.as_of for o in obs} == {date(2026, 10, 9)}
    assert [(o.source_key, o.value, o.field, o.unit) for o in obs][:2] == [
        ("1M", Decimal("0.039012"), "parrate", "decimal"), ("3M", Decimal("0.038544"), "parrate", "decimal")]
    (rec,) = recs
    assert (rec.record_type, rec.source_key, rec.as_of) == ("curve", "2026-10-09", date(2026, 10, 9))
    f = rec.fields
    assert (f["effectiveasof"], f["currency"], f["baddayconvention"], f["spotdate"], f["snaptime"]) == (
        "2026-10-12", "USD", "M", "2026-10-14", "2026-10-09T16:00:00")
    assert (f["fixeddaycountconvention"], f["floatingdaycountconvention"], f["fixedpaymentfrequency"],
            f["floatingpaymentfrequency"], f["calendars"]) == ("ACT/360", "ACT/360", "1Y", "1Y", ["NYM"])
    assert f["curvepoints"][4] == {"tenor": "10Y", "maturitydate": "2036-10-14", "parrate": "0.036912"}


def test_the_xml_is_picked_out_of_the_zip():
    assert len(p.parse_curve(zipped(curve_xml(), extra=()), "USD")[0]) == len(POINTS)
    with pytest.raises(ParseError, match="expected one .xml file"):
        p.parse_curve(zipped(curve_xml(), extra=("InterestRates_USD_20261008.xml",)), "USD")


def test_plain_xml_and_any_root_name_are_read():
    obs, _ = p.parse_curve(curve_xml(root="SPGMI"), "USD")
    assert len(obs) == len(POINTS)


@pytest.mark.parametrize(("body", "ccy", "match"), [
    (zipped(curve_xml(ccy="GBP")), "USD", "a GBP curve, expected USD"),
    (zipped(curve_xml(), name="InterestRates_USD_20261008.xml"), "USD", "dated 2026-10-08"),
    (zipped(curve_xml(points=[("1M", "2026-11-13", "x")])), "USD", "isn't a number"),
    (zipped(curve_xml(points=[("1M", "2026-11-13", "0.01"), ("1M", "2026-11-13", "0.01")])), "USD", "twice"),
    (zipped(curve_xml(points=[])), "USD", "no curve points"),
    (zipped(curve_xml(points=[("1M", "2026-10-01", "0.01")])), "USD", "isn't after the trade date"),
    (b"Interest Rates not available", "USD", "neither a zip nor XML"),
    (b"PK\x03\x04garbage", "USD", "not a readable zip"),
])
def test_bad_files(body, ccy, match):
    with pytest.raises(ParseError, match=match):
        p.parse_curve(body, ccy)


def test_the_view_ignores_the_zip_wrapper():
    xml = curve_xml()
    assert p.curve_view(zipped(xml, when=(2026, 10, 9, 16, 50, 0))) == p.curve_view(zipped(xml, when=(2026, 10, 10,
                                                                                                         9, 0, 0)))
    with pytest.raises(ValueError):
        p.curve_view(b"nope")


def test_previous_weekday():
    assert p.previous_weekday(date(2026, 10, 12)) == date(2026, 10, 9)  # Monday -> Friday
    assert p.previous_weekday(date(2026, 10, 13)) == date(2026, 10, 12)


# --- sources and fetch ------------------------------------------------------------------------------------------


def test_sources():
    assert set(sw.SOURCES) == {f"SPGMI-RFR-{c}" for c in ("USD", "EUR", "GBP", "JPY", "CHF", "AUD")}
    usd = sw.SOURCES["SPGMI-RFR-USD"]
    assert usd.url("2026-05-20") == "https://rfr.spglobal.com/InterestRates_USD_20260520.zip"
    assert "email" not in usd.spec.url
    assert (usd.kind, usd.shape, usd.calendar) == ("day", "curve", "FED")
    assert all(s.spec.pulls and s.spec.parse for s in sw.SOURCES.values())
    assert sw.check_period("SPGMI-RFR-GBP", "2026-10-09", NOW) == "2026-10-09"
    for period in ("2026-10", "2026-10-10x", "2020-01-02"):
        with pytest.raises(sec.BadPeriod):
            sw.check_period("SPGMI-RFR-USD", period, NOW)


@pytest.fixture
def email(monkeypatch):
    monkeypatch.setattr(config, "settings", Settings(spgmi_rfr_email=EMAIL))


def test_fetch_adds_the_email_and_keeps_it_out_of_errors(email, monkeypatch):
    seen = []
    body = zipped(curve_xml())

    def get(url):
        seen.append(url)
        return 200, "application/zip", body

    monkeypatch.setattr(sw, "_get", get)
    assert sw.fetch_spgmi("https://rfr.spglobal.com/InterestRates_USD_20261009.zip")[2] == body
    assert seen == [f"https://rfr.spglobal.com/InterestRates_USD_20261009.zip?email={EMAIL}"]

    for answer, marker in [
        (b"Interest Rates not available, please check date and/or currency entered", sw.NOT_PUBLISHED),
        (b"Username not known, please check username", sw.TERMS),
        (b"Accept/re-accept terms of use. Go to https://rfr.spglobal.com to accept the terms of use", sw.TERMS),
        (f"Unable to generate interest rate report at this time for {EMAIL}".encode(), "not a curve file"),
    ]:
        monkeypatch.setattr(sw, "_get", lambda url, a=answer: (200, "text/plain", a))
        with pytest.raises(service.SourceFetchError, match=marker) as e:
            sw.fetch_spgmi("https://rfr.spglobal.com/x.zip")
        assert EMAIL not in str(e.value)

    def boom(url):
        raise service.SourceFetchError(f"connect failed for {url}")

    monkeypatch.setattr(sw, "_get", boom)
    with pytest.raises(service.SourceFetchError) as e:
        sw.fetch_spgmi("https://rfr.spglobal.com/x.zip")
    assert EMAIL not in str(e.value) and "<email>" in str(e.value)


def test_no_email_is_a_failed_fetch(monkeypatch):
    monkeypatch.setattr(config, "settings", Settings(spgmi_rfr_email=None))
    with pytest.raises(service.SourceFetchError, match="SPGMI_RFR_EMAIL isn't set"):
        sw.fetch_spgmi("https://rfr.spglobal.com/x.zip")


# --- capture, near-raw, readers ---------------------------------------------------------------------------------


def test_capture_parses_to_observations_and_a_record(migrated_db, email, monkeypatch):
    answers = [zipped(curve_xml()), zipped(curve_xml(), when=(2026, 10, 10, 8, 0, 0))]
    monkeypatch.setattr(sw, "_get", lambda url: (200, "application/zip", answers.pop(0)))
    with db.session() as s:
        r = sw.run_capture(s, "SPGMI-RFR-USD", "2026-10-09")
    assert r["new_capture"] and r["parsed"] and r["values"] == len(POINTS) and r["added"] == len(POINTS)
    assert r["record"]["added"] == 1
    with db.session() as s:
        again = sw.run_capture(s, "SPGMI-RFR-USD", "2026-10-09")  # re-zipped, same XML: unchanged
        assert not again["new_capture"] and again["added"] == 0
        assert s.scalar(select(func.count()).select_from(Capture)) == 1
        assert s.scalar(select(func.count()).select_from(Observation)) == len(POINTS)
        rec = s.scalars(select(Record)).one()
        assert rec.fields["calendars"] == ["NYM"] and rec.period == "2026-10-09"
        state = next(x for x in source_status.list_sources(s) if x["name"] == "SPGMI-RFR-USD")
        assert (state["group"], state["parsed"], state["dag"]) == ("swaps", True, "mkt_data__swap_curves_capture")
        assert "SPGMI-RFR-USD" in {x["name"] for x in obs_api.list_sources(s)}
        assert "SPGMI-RFR-USD" in {x["name"] for x in rec_api.list_sources(s)}


def test_a_corrected_curve_is_a_revision_and_rebuild_replays_it(migrated_db, email, monkeypatch):
    fixed = [(t, m, "0.0400" if t == "1M" else r) for t, m, r in POINTS]
    answers = [zipped(curve_xml()), zipped(curve_xml(points=fixed))]
    monkeypatch.setattr(sw, "_get", lambda url: (200, "application/zip", answers.pop(0)))
    with db.session() as s:
        sw.run_capture(s, "SPGMI-RFR-USD", "2026-10-09")
        r = sw.run_capture(s, "SPGMI-RFR-USD", "2026-10-09")
    assert r["new_capture"] and r["changed"] == 1 and r["record"]["changed"] == 1
    with db.session() as s:
        out = sw.run_rebuild(s, "SPGMI-RFR-USD")
        assert out["applied"] == 2 and out["record"]["applied"] == 2
        cur = s.scalar(select(Observation.value).where(Observation.source_key == "1M", Observation.valid_to.is_(None)))
        assert cur == Decimal("0.0400")


def test_not_published_stores_nothing(migrated_db, email, monkeypatch):
    monkeypatch.setattr(sw, "_get", lambda url: (200, "text/plain", b"Interest Rates not available, please check"))
    with db.session() as s, pytest.raises(service.SourceFetchError, match=sw.NOT_PUBLISHED):
        sw.run_capture(s, "SPGMI-RFR-EUR", "2026-10-09")
    with db.session() as s:
        assert s.scalar(select(func.count()).select_from(Capture)) == 0
        assert s.scalars(select(SourceCheck)).one().outcome == "error"


def test_job(migrated_db, email, monkeypatch):
    monkeypatch.setattr(jobs, "settings", Settings(airflow_token=TOKEN, read_token="read-token"))
    monkeypatch.setattr(sw, "_get", lambda url: (200, "application/zip", zipped(curve_xml())))
    auth = {"Authorization": f"Bearer {TOKEN}"}
    r = client.post("/jobs/swaps/spgmi-rfr-usd/capture?period=2026-10-09", headers=auth)
    assert r.status_code == 200 and r.json()["values"] == len(POINTS)
    assert client.post("/jobs/swaps/nope/capture", headers=auth).status_code == 404
    assert client.post("/jobs/swaps/SPGMI-RFR-USD/capture?period=2026-10", headers=auth).status_code == 400
    r = client.post("/jobs/swaps/SPGMI-RFR-GBP/capture?period=2026-10-09", headers=auth)  # a USD file
    assert r.status_code == 422
    assert client.post("/jobs/swaps/SPGMI-RFR-USD/rebuild", headers=auth).json()["applied"] == 1
    monkeypatch.setattr(sw, "_get", lambda url: (200, "text/plain", b"Username not known, please check username"))
    r = client.post("/jobs/swaps/SPGMI-RFR-JPY/capture?period=2026-10-09", headers=auth)
    assert r.status_code == 502 and sw.TERMS in r.json()["detail"]


# --- ISDA's calendars -------------------------------------------------------------------------------------------


def test_isda_calendar_files():
    cal = isda.parse_dates(b"20220620\r\n20330620\n20390620\n\n", "NYM")
    assert cal.years[0] == 1990 and cal.years[-1] == 2100
    assert [d.day for d in cal.days] == [date(2022, 6, 20), date(2033, 6, 20), date(2039, 6, 20)]
    assert cal.days[0].holiday == "ISDA NYM holiday" and cal.days[0].status == "closed"
    # A weekend date changes nothing and is skipped (2026-06-20 is a Saturday).
    assert [d.day for d in isda.parse_dates(b"20260620\n20260622\n", "TYO").days] == [date(2026, 6, 22)]
    for bad, match in [(b"2022-06-20\n", "isn't a YYYYMMDD"), (b"20221340\n", "isn't a date"), (b"", "no dates"),
                       (b"20220620\n20220620\n", "twice"), (b"21010620\n", "outside")]:
        with pytest.raises(ParseError, match=match):
            isda.parse_dates(bad, "NYM")


def test_isda_calendars_are_registered():
    assert [s.name for s in service.CALENDARS["ISDA-NYM"].sources] == ["ISDA-NYM-CSV"]
    assert service.CALENDARS["ISDA-TYO"].sources[0].url == "https://www.cdsmodel.com/assets/cds-model/csv/TYO.csv"
    for name in ("ISDA-NYM", "ISDA-TYO"):
        assert source_status.CALENDAR_SCHEDULES[name].dag == "mkt_data__isda_calendars"
