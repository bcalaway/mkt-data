from datetime import date, time

import pytest

from app.calendars import sifma
from app.calendars.parsed import Day, ParseError


def _days(html):
    return {d.day: d for d in sifma.parse(html).days}


def test_parses_the_us_section(sifma_html):
    p = sifma.parse(sifma_html)
    # Only 2026 has a full set; the 2027 tab isn't in the page yet.
    assert p.years == (2026,)
    closed = [d for d in p.days if d.status == "closed"]
    early = [d for d in p.days if d.status == "early_close"]
    # 11 full closes in 2026 (Good Friday is an early close) plus Jan 1, 2027.
    assert len([d for d in closed if d.day.year == 2026]) == 11
    assert len(early) == 7
    assert all(d.close_time is None for d in closed)
    assert all(d.close_time is not None for d in early)


def test_full_and_early_closes(sifma_html):
    days = _days(sifma_html)
    assert days[date(2026, 5, 25)].status == "closed"
    assert days[date(2026, 5, 25)].holiday == "Memorial Day"
    eve = days[date(2026, 5, 22)]
    assert (eve.status, eve.close_time, eve.holiday) == ("early_close", time(14), "Memorial Day (early close)")


def test_good_friday_2026_is_an_early_close_only(sifma_html):
    gf = _days(sifma_html)[date(2026, 4, 3)]
    assert (gf.status, gf.close_time) == ("early_close", time(12))


def test_new_years_entries_span_the_year_boundary(sifma_html):
    days = _days(sifma_html)
    assert days[date(2025, 12, 31)].holiday == "New Year's Day (early close)"  # year pair and curly quote gone
    assert days[date(2026, 12, 31)].close_time == time(14)
    assert days[date(2027, 1, 1)].status == "closed"


def test_the_uk_section_is_ignored(sifma_html):
    assert date(2026, 4, 6) not in _days(sifma_html)  # Easter Monday, U.K. only


def test_weekday_must_match_the_date(sifma_html):
    broken = sifma_html.replace(b"Monday, January 19, 2026", b"Tuesday, January 19, 2026")
    with pytest.raises(ParseError, match="is a Monday, not a Tuesday"):
        sifma.parse(broken)


def test_unreadable_early_close(sifma_html):
    broken = sifma_html.replace(b"Early Close (12:00 p.m. Eastern Time):", b"Early Close (noon-ish):")
    with pytest.raises(ParseError, match="can't read"):
        sifma.parse(broken)


def test_split_early_close_label_is_joined(sifma_html):
    split = sifma_html.replace(
        b"<strong>Early Close (12:00 p.m. Eastern Time):</strong> Friday, April 3, 2026",
        b"<span>Early Close (12:00 p.m. Eastern Time):</span></p><p>Friday, April 3, 2026",
    )
    assert _days(split)[date(2026, 4, 3)].close_time == time(12)


def test_identical_duplicates_are_fine_but_conflicts_fail(sifma_html):
    item = (
        b'<div class="holiday-item"><h3>New Year\xe2\x80\x99s Day 2026/2027</h3>'
        b"<p>Friday, January 1, 2027</p></div>"
    )
    marker = b'      </div>\n    </section>\n    <section id="uk">'
    assert marker in sifma_html
    dup = sifma_html.replace(marker, item + marker, 1)
    assert date(2027, 1, 1) in _days(dup)
    conflict = sifma_html.replace(marker, item.replace(b"Day 2026/2027", b"Day Again") + marker, 1)
    with pytest.raises(ParseError, match="listed twice"):
        sifma.parse(conflict)


def test_partial_year_is_not_covered(sifma_html):
    for d in [b"Monday, September 7, 2026", b"Monday, October 12, 2026", b"Wednesday, November 11, 2026"]:
        sifma_html = sifma_html.replace(b"<p class=\"holiday-item__date\">" + d + b"</p>", b"")
    with pytest.raises(ParseError, match="no year with at least"):
        sifma.parse(sifma_html)


def test_no_us_section():
    with pytest.raises(ParseError, match="no 'U.S. Holiday Recommendations'"):
        sifma.parse(b"<html><h2>U.K. Holiday Recommendations</h2><p>Monday, April 6, 2026</p></html>")


# --- The U.S. Holiday Archive (parse_archive)


def test_archive_covers_2015_to_2025(sifma_archive_html):
    p = sifma.parse_archive(sifma_archive_html)
    assert p.years == tuple(range(2015, 2026))
    days = {d.day: d for d in p.days}
    assert days[date(2014, 12, 31)].status == "early_close"  # stored, but 2014 isn't covered
    assert days[date(2024, 7, 3)] == Day(date(2024, 7, 3), "early_close", "U.S. Independence Day (early close)", time(14))


def test_archive_early_close_formats(sifma_archive_html):
    days = {d.day: d for d in sifma.parse_archive(sifma_archive_html).days}
    # "Early Close Only (12:00 p.m. …): Friday, April 2, 2021 – Confirmed based on …"
    assert (days[date(2021, 4, 2)].status, days[date(2021, 4, 2)].close_time) == ("early_close", time(12))
    # "Early Close (12:00 Noon Eastern Time) Friday, April 3, 2015" (no colon)
    assert days[date(2015, 4, 3)].close_time == time(12)
    # New Year's Day 2022 fell on a Saturday: only the Dec 31, 2021 early close.
    assert days[date(2021, 12, 31)].close_time == time(14) and date(2022, 1, 1) not in days


def test_archive_year_sections_overlap_cleanly(sifma_archive_html):
    # "New Year's Day 2020/2021" ends the 2020 section and starts 2021's: listed twice, identically.
    assert sifma_archive_html.count(b"Thursday, December 31, 2020") == 2
    days = [d.day for d in sifma.parse_archive(sifma_archive_html).days]
    assert days.count(date(2020, 12, 31)) == 1


def test_archive_year_with_a_missed_line_fails(sifma_archive_html):
    broken = sifma_archive_html.replace(b"<p>Monday, September 2, 2019</p>", b"<p>Labor Day: see notice</p>")
    broken = broken.replace(b"<p>Monday, October 14, 2019</p>", b"")
    broken = broken.replace(b"<p>Monday, November 11, 2019</p>", b"")
    with pytest.raises(ParseError, match="too few full closes"):
        sifma.parse_archive(broken)


def test_noon_must_be_twelve(sifma_archive_html):
    broken = sifma_archive_html.replace(b"(12:00 Noon Eastern Time)", b"(11:00 Noon Eastern Time)")
    with pytest.raises(ParseError, match="noon"):
        sifma.parse_archive(broken)


def test_archive_needs_year_headings():
    with pytest.raises(ParseError, match="no year headings"):
        sifma.parse_archive(b"<html><h1>US Holiday Archive</h1><p>Monday, May 25, 2015</p></html>")
