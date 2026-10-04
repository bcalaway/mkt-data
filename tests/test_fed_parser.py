from datetime import date

import pytest

from app.calendars import fed
from app.calendars.parsed import ParseError


def test_parses_the_k8_table(fed_html):
    p = fed.parse(fed_html)
    assert p.years == (2026, 2027, 2028, 2029, 2030)
    # 55 holidays, 5 of them on a Saturday (no weekday closure for the Banks).
    assert len(p.days) == 50
    assert all(d.status == "closed" and d.close_time is None for d in p.days)


def test_sunday_holiday_closes_the_monday(fed_html):
    days = {d.day: d for d in fed.parse(fed_html).days}
    # The page's own footnote: closed July 5, 2027 and November 12, 2029.
    assert days[date(2027, 7, 5)].holiday == "Independence Day (observed)"
    assert days[date(2029, 11, 12)].holiday == "Veterans Day (observed)"
    assert date(2027, 7, 4) not in days


def test_saturday_holiday_closes_no_weekday(fed_html):
    days = {d.day for d in fed.parse(fed_html).days}
    # July 4, 2026 is a Saturday: the Reserve Banks are open Friday July 3.
    assert date(2026, 7, 3) not in days and date(2026, 7, 4) not in days
    assert date(2027, 12, 24) not in days and date(2027, 12, 31) not in days


def test_marker_must_match_the_weekday(fed_html):
    # July 4, 2027 is a Sunday; drop its ** and the parser must refuse.
    broken = fed_html.replace(b"<td>July 4**</td>", b"<td>July 4</td>")
    with pytest.raises(ParseError, match="doesn't match its weekday"):
        fed.parse(broken)


def test_unreadable_date(fed_html):
    with pytest.raises(ParseError, match="can't read date"):
        fed.parse(fed_html.replace(b"<td>May 25</td>", b"<td>TBD</td>"))


def test_no_year_table():
    with pytest.raises(ParseError, match="no table"):
        fed.parse(b"<html><table><tr><td>a</td><td>b</td></tr></table></html>")


def _drop_row(html: bytes, holiday: bytes) -> bytes:
    start = html.index(b'<tr><th scope="row">' + holiday)
    end = html.index(b"</tr>", start) + len(b"</tr>")
    return html[:start] + html[end:]


def test_missing_holiday_rows(fed_html):
    trimmed = _drop_row(_drop_row(fed_html, b"Labor Day"), b"Columbus Day")
    with pytest.raises(ParseError, match="too few holidays"):
        fed.parse(trimmed)
