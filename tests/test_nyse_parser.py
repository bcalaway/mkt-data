from datetime import date, time

import pytest

from app.calendars import nyse
from app.calendars.parsed import ParseError


def _days(html):
    return {d.day: d for d in nyse.parse(html).days}


def test_parses_three_years(nyse_html):
    p = nyse.parse(nyse_html)
    assert p.years == (2026, 2027, 2028)
    closed = [d for d in p.days if d.status == "closed"]
    early = [d for d in p.days if d.status == "early_close"]
    per_year = {y: sum(1 for d in closed if d.day.year == y) for y in p.years}
    # 2028 has no New Year's Day holiday (Jan 1 is a Saturday).
    assert per_year == {2026: 10, 2027: 10, 2028: 9}
    assert sorted(d.day for d in early) == [
        date(2026, 11, 27), date(2026, 12, 24), date(2027, 11, 26), date(2028, 7, 3), date(2028, 11, 24),
    ]
    assert all(d.close_time == time(13) for d in early)  # the equities close, not options' 1:15
    assert all(d.close_time is None for d in closed)


def test_names_and_observed_days(nyse_html):
    days = _days(nyse_html)
    assert days[date(2026, 4, 3)].status == "closed"  # Good Friday: NYSE closes (SIFMA: noon)
    assert days[date(2026, 2, 16)].holiday == "Washington's Birthday"  # curly quote gone
    assert days[date(2026, 7, 3)].holiday == "Independence Day (observed)"
    assert days[date(2027, 12, 24)].holiday == "Christmas Day (observed)"
    assert days[date(2027, 6, 18)].holiday == "Juneteenth National Independence Day (observed)"
    assert date(2027, 12, 31) not in days  # no Friday observance for a Saturday New Year's Day


def test_early_closes_are_named_after_their_holiday(nyse_html):
    days = _days(nyse_html)
    assert days[date(2026, 11, 27)].holiday == "Thanksgiving Day (early close)"
    assert days[date(2026, 12, 24)].holiday == "Christmas Day (early close)"
    assert days[date(2028, 7, 3)].holiday == "Independence Day (early close)"


def test_script_text_is_ignored(nyse_html):
    assert date(2025, 11, 28) not in _days(nyse_html)


def test_footnotes_inside_the_table_work_too(nyse_html):
    # Every footnote as a one-cell row at the end of the holidays table.
    table_end = nyse_html.index(b"</tbody>")
    notes_end = nyse_html.index(b"</section>", table_end)
    notes = nyse_html[table_end:notes_end].replace(b"</tbody>\n      </table>", b"")
    notes = notes.replace(b"<p>", b"<tr><td colspan=4>").replace(b"</p>", b"</td></tr>")
    assert notes.count(b"<tr>") == 4
    moved = nyse_html[:table_end] + notes + b"</tbody></table>" + nyse_html[notes_end:]
    assert nyse.parse(moved) == nyse.parse(nyse_html)


def test_weekday_must_match_the_date(nyse_html):
    broken = nyse_html.replace(b"Monday, January 19<", b"Tuesday, January 19<")
    with pytest.raises(ParseError, match="is a Monday, not a Tuesday"):
        nyse.parse(broken)


def test_unreadable_cell(nyse_html):
    broken = nyse_html.replace(b"Monday, September 7<", b"First Monday in September<")
    with pytest.raises(ParseError, match="can't read"):
        nyse.parse(broken)


def test_marker_without_an_early_close_fails(nyse_html):
    # The Christmas Eve footnote reworded so it no longer says "close early at".
    broken = nyse_html.replace(
        b"close early at 1:00 p.m. (1:15 p.m. for eligible options) on Thursday, December 24, 2026",
        b"have a shortened session on Thursday, December 24, 2026",
    )
    with pytest.raises(ParseError, match="Christmas Day 2026-12-25 has a footnote marker"):
        nyse.parse(broken)


def test_early_close_far_from_any_holiday_fails(nyse_html):
    broken = nyse_html.replace(b"Thursday, December 24, 2026", b"Thursday, October 15, 2026")
    with pytest.raises(ParseError, match="isn't next to any listed holiday"):
        nyse.parse(broken)


def test_early_close_on_a_holiday_fails(nyse_html):
    broken = nyse_html.replace(b"Thursday, December 24, 2026", b"Friday, December 25, 2026")
    with pytest.raises(ParseError, match="both a holiday and an early close"):
        nyse.parse(broken)


def test_missing_rows_fail(nyse_html):
    start = nyse_html.index(b"<tr><td>Labor Day")
    end = nyse_html.index(b"</tr>", start) + len(b"</tr>")
    with pytest.raises(ParseError, match="too few holidays"):
        nyse.parse(nyse_html[:start] + nyse_html[end:])


def test_no_holiday_table():
    with pytest.raises(ParseError, match="no holiday table"):
        nyse.parse(b"<html><table><tr><th>Session</th><th>NYSE</th></tr></table></html>")
