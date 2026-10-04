"""SQLAlchemy models (docs/phase-1.md, step 3).

Two layers:

- **Raw** (`source`, `capture`, `source_check`): what was fetched, from
  where, when, byte for byte. `capture` is append-only: a Postgres trigger
  (migration 0002) refuses UPDATE, DELETE and TRUNCATE. Raw is kept forever.
- **Processed** (`calendar`, `calendar_year`, `calendar_day`): parsed from
  raw and always rebuildable from it. `calendar_day` keeps history: a date
  that changes or disappears in a newer capture gets `valid_to` set and a
  new row, never an overwrite. The current view is `valid_to IS NULL`.

Integer IDs internally; every table people look at has a short readable
`name`. Every change here needs a matching Alembic migration
(`tests/test_migrations.py` checks).
"""

from datetime import date, datetime, time

from sqlalchemy import (
    CheckConstraint,
    Date,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    LargeBinary,
    SmallInteger,
    String,
    Text,
    Time,
    func,
    text,
)
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column


class Base(DeclarativeBase):
    pass


class Source(Base):
    """A place raw data comes from (one URL, one format)."""

    __tablename__ = "source"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    name: Mapped[str] = mapped_column(String(40), unique=True)  # e.g. FED-K8
    url: Mapped[str] = mapped_column(Text)
    description: Mapped[str] = mapped_column(Text)


class Capture(Base):
    """One distinct version of a source's content. Append-only, kept forever."""

    __tablename__ = "capture"
    __table_args__ = (Index("ix_capture_source_fetched", "source_id", "fetched_at"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    source_id: Mapped[int] = mapped_column(Integer, ForeignKey("source.id"))
    fetched_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    http_status: Mapped[int] = mapped_column(SmallInteger)
    content_type: Mapped[str | None] = mapped_column(String(200))
    sha256: Mapped[str] = mapped_column(String(64))
    size_bytes: Mapped[int] = mapped_column(Integer)
    body: Mapped[bytes] = mapped_column(LargeBinary)


class SourceCheck(Base):
    """Every fetch attempt (new content, unchanged content, or an error) and every reparse.

    `parse_outcome` is whether that check's parse worked ('ok' / 'error', the
    error in `parse_detail`); empty for a fetch error or a source with no parser.
    """

    __tablename__ = "source_check"
    __table_args__ = (
        Index("ix_source_check_source_checked", "source_id", "checked_at"),
        CheckConstraint("outcome IN ('new', 'unchanged', 'error', 'reparse')", name="ck_source_check_outcome"),
        CheckConstraint("parse_outcome IN ('ok', 'error')", name="ck_source_check_parse_outcome"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    source_id: Mapped[int] = mapped_column(Integer, ForeignKey("source.id"))
    checked_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    outcome: Mapped[str] = mapped_column(String(12))
    capture_id: Mapped[int | None] = mapped_column(Integer, ForeignKey("capture.id"))
    detail: Mapped[str | None] = mapped_column(Text)
    parse_outcome: Mapped[str | None] = mapped_column(String(8))
    parse_detail: Mapped[str | None] = mapped_column(Text)


class Calendar(Base):
    """A market or institution's holiday calendar, e.g. FED, SIFMA-US, NYSE."""

    __tablename__ = "calendar"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    name: Mapped[str] = mapped_column(String(20), unique=True)
    description: Mapped[str] = mapped_column(Text)
    timezone: Mapped[str] = mapped_column(String(40))


class CalendarYear(Base):
    """A year this calendar has published dates for (coverage), and from which capture."""

    __tablename__ = "calendar_year"

    calendar_id: Mapped[int] = mapped_column(Integer, ForeignKey("calendar.id"), primary_key=True)
    year: Mapped[int] = mapped_column(SmallInteger, primary_key=True)
    capture_id: Mapped[int] = mapped_column(Integer, ForeignKey("capture.id"))
    first_seen_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class CalendarDay(Base):
    """A weekday the calendar is closed or closes early. Weekends are implicit."""

    __tablename__ = "calendar_day"
    __table_args__ = (
        CheckConstraint("status IN ('closed', 'early_close')", name="ck_calendar_day_status"),
        CheckConstraint(
            "(status = 'early_close') = (close_time IS NOT NULL)", name="ck_calendar_day_close_time"
        ),
        # One current row per calendar and date; superseded rows keep valid_to.
        Index(
            "uq_calendar_day_current",
            "calendar_id",
            "day",
            unique=True,
            postgresql_where=text("valid_to IS NULL"),
            sqlite_where=text("valid_to IS NULL"),
        ),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    calendar_id: Mapped[int] = mapped_column(Integer, ForeignKey("calendar.id"))
    day: Mapped[date] = mapped_column(Date)
    status: Mapped[str] = mapped_column(String(12))
    close_time: Mapped[time | None] = mapped_column(Time)
    holiday: Mapped[str] = mapped_column(String(100))
    capture_id: Mapped[int] = mapped_column(Integer, ForeignKey("capture.id"))
    valid_from: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    valid_to: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
