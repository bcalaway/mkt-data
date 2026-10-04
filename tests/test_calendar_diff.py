from datetime import date

from app.calendars.parsed import Day, ParsedCalendar, diff


def _day(y, m, d, name="Holiday"):
    return Day(date(y, m, d), "closed", name)


def test_new_changed_removed_within_parsed_years():
    current = {
        date(2026, 1, 1): _day(2026, 1, 1, "New Year's Day"),
        date(2026, 5, 25): _day(2026, 5, 25, "Memorial Day"),
        date(2026, 12, 24): _day(2026, 12, 24, "Christmas Eve"),
    }
    parsed = ParsedCalendar(
        years=(2026, 2027),
        days=(
            _day(2026, 1, 1, "New Year's Day"),  # unchanged
            _day(2026, 5, 25, "Memorial Day (renamed)"),  # changed
            _day(2027, 1, 1, "New Year's Day"),  # added
        ),
    )
    d = diff(current, parsed)
    assert [x.day for x in d.added] == [date(2027, 1, 1)]
    assert [x.day for x in d.changed] == [date(2026, 5, 25)]
    assert d.removed == (date(2026, 12, 24),)


def test_years_that_rolled_off_the_source_are_kept():
    current = {date(2025, 12, 25): _day(2025, 12, 25)}
    parsed = ParsedCalendar(years=(2026,), days=(_day(2026, 12, 25),))
    d = diff(current, parsed)
    assert d.removed == ()
    assert [x.day for x in d.added] == [date(2026, 12, 25)]


def test_identical_parse_is_a_no_op():
    days = (_day(2026, 1, 1), _day(2026, 7, 3))
    d = diff({x.day: x for x in days}, ParsedCalendar((2026,), days))
    assert d.added == d.changed == d.removed == ()
