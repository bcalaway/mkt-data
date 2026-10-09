"""Phase 4's fixings parsers (app/futures/parsers.py), on captures shaped like the hub's (2026-10-08)."""

from datetime import date
from decimal import Decimal

import pytest
from sqlalchemy import select

from app import db
from app.calendars import service
from app.calendars.parsed import ParseError
from app.futures import parsers as p
from app.futures import sources as fut
from app.models import Observation

SOFR = b"""{
 "refRates": [
  {"effectiveDate": "2026-10-07", "type": "SOFR", "percentRate": 3.88, "percentPercentile1": 3.81,
   "percentPercentile25": 3.86, "percentPercentile75": 3.92, "percentPercentile99": 3.96, "volumeInBillions": 2968,
   "revisionIndicator": ""},
  {"effectiveDate": "2026-10-06", "type": "SOFR", "percentRate": 3.9, "percentPercentile1": 3.84,
   "percentPercentile25": 3.88, "percentPercentile75": 3.95, "percentPercentile99": 3.98, "volumeInBillions": 2997,
   "revisionIndicator": ""}
 ]
}"""
EFFR = b"""{"refRates": [{"effectiveDate": "2026-10-07", "type": "EFFR", "percentRate": 3.88, "percentPercentile1": 3.85,
 "percentPercentile25": 3.87, "percentPercentile75": 3.88, "percentPercentile99": 3.89, "targetRateFrom": 3.75,
 "targetRateTo": 4.0, "volumeInBillions": 108, "revisionIndicator": ""}]}"""
H10_RATES = (
    b'"Series Description","Euro-Area Euro","Japanese Yen"\n'
    b'"Unit:","Currency","Currency"\n'
    b'"Multiplier:","1","1"\n'
    b'"Currency:","EUR","JPY"\n'
    b'"Unique Identifier: ","H10/H10/RXI$US_N.B.EU","H10/H10/RXI_N.B.JA"\n'
    b'"Time Period","RXI$US_N.B.EU","RXI_N.B.JA"\n'
    b"2026-09-04,1.1618,156.1100\n"
    b"2026-09-07,ND,ND\n"
    b"2026-09-08,1.1627,154.2400\n"
)
H10_INDEXES = (
    b'"Series Description","Nominal Broad U.S. Dollar Index"\n'
    b'"Unit:","Index:_January_2006_100"\n'
    b'"Multiplier:","1"\n'
    b'"Currency:","NA"\n'
    b'"Unique Identifier: ","H10/H10/JRXWTFB_N.B"\n'
    b'"Time Period","JRXWTFB_N.B"\n'
    b"2026-09-04,121.5432\n"
)
ECB = (
    b"KEY,FREQ,CURRENCY,CURRENCY_DENOM,EXR_TYPE,EXR_SUFFIX,TIME_PERIOD,OBS_VALUE,OBS_STATUS,TITLE\n"
    b"EXR.D.AUD.EUR.SP00.A,D,AUD,EUR,SP00,A,2026-10-01,1.6255,A,Australian dollar/Euro ECB reference exchange rate\n"
    b"EXR.D.AUD.EUR.SP00.A,D,AUD,EUR,SP00,A,2026-10-06,1.614,A,Australian dollar/Euro ECB reference exchange rate\n"
    b"EXR.D.JPY.EUR.SP00.A,D,JPY,EUR,SP00,A,2026-10-06,,A,Japanese yen/Euro ECB reference exchange rate\n"
)


def test_sofr_keeps_every_number_as_printed():
    obs = p.parse_sofr(SOFR)
    got = {(o.as_of, o.field): (o.value, o.unit) for o in obs}
    assert got[(date(2026, 10, 6), "percentRate")] == (Decimal("3.9"), "percent")
    assert str(got[(date(2026, 10, 6), "percentRate")][0]) == "3.9"  # the printed digits, no float
    assert got[(date(2026, 10, 7), "volumeInBillions")] == (Decimal(2968), "USD billions")
    assert {o.source_key for o in obs} == {"SOFR"} and len(obs) == 12


def test_a_value_marked_na_is_skipped():
    body = (b'{"refRates": [{"effectiveDate": "2019-05-31", "type": "SOFR", "percentRate": 2.35, '
            b'"percentPercentile1": "NA", "volumeInBillions": 1066}]}')
    assert {o.field for o in p.parse_sofr(body)} == {"percentRate", "volumeInBillions"}


def test_effr_has_the_target_range():
    got = {o.field: o.value for o in p.parse_effr(EFFR)}
    assert got["targetRateFrom"] == Decimal("3.75") and got["targetRateTo"] == Decimal("4.0")


def test_the_wrong_rate_or_shape_is_refused():
    with pytest.raises(ParseError, match="expected EFFR"):
        p.parse_effr(SOFR)
    with pytest.raises(ParseError):
        p.parse_sofr(b"<html>")


def test_h10_rates_by_series_skipping_no_data():
    obs = p.parse_ddp(H10_RATES)
    assert [(o.source_key, str(o.as_of), str(o.value), o.unit) for o in obs] == [
        ("RXI$US_N.B.EU", "2026-09-04", "1.1618", "EUR currency"), ("RXI_N.B.JA", "2026-09-04", "156.1100", "JPY currency"),
        ("RXI$US_N.B.EU", "2026-09-08", "1.1627", "EUR currency"), ("RXI_N.B.JA", "2026-09-08", "154.2400", "JPY currency")]


def test_h10_indexes():
    (o,) = p.parse_ddp(H10_INDEXES)
    assert (o.source_key, o.value, o.unit) == ("JRXWTFB_N.B", Decimal("121.5432"), "index")


def test_ecb_rates_skip_blank_values():
    obs = p.parse_ecb(ECB)
    assert [(o.source_key, str(o.as_of), str(o.value), o.unit) for o in obs] == [
        ("EXR.D.AUD.EUR.SP00.A", "2026-10-01", "1.6255", "AUD per EUR"),
        ("EXR.D.AUD.EUR.SP00.A", "2026-10-06", "1.614", "AUD per EUR")]
    with pytest.raises(ParseError, match="missing columns"):
        p.parse_ecb(b"A,B\n1,2\n")


def test_a_capture_becomes_observations(migrated_db, monkeypatch):
    monkeypatch.setattr(service, "fetch", lambda url: (200, "application/json", SOFR))
    with db.session() as s:
        r = fut.run_capture(s, "NYFED-SOFR", "2026-10")
    assert r["new_capture"]
    with db.session() as s:
        rows = s.scalars(select(Observation).where(Observation.field == "percentRate")).all()
        assert sorted((str(x.as_of), x.value) for x in rows) == [("2026-10-06", Decimal("3.9")), ("2026-10-07", Decimal("3.88"))]
