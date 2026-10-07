"""SQLAlchemy models (docs/phase-1.md step 3, docs/phase-2.md Part A).

Two layers:

- **Raw** (`source`, `capture`, `source_check`): what was fetched, from
  where, when, byte for byte. `capture` is append-only: a Postgres trigger
  (migration 0002) refuses UPDATE, DELETE and TRUNCATE. Raw is kept forever.
- **Near-raw** (`source_year`, `source_day`): each calendar source's parse
  as that source states it, one set of rows per source, no precedence
  (docs/phase-2.md, Part A). What calendar-svc builds golden calendars from.
  Rebuildable from raw.

Near-raw keeps history: a date that changes or disappears in a newer capture
gets `valid_to` set and a new row, never an overwrite. The current view is
`valid_to IS NULL`.

The golden calendars (one per market, precedence applied) live in
calendar-svc since phase 2, step A5; migration 0005 dropped mkt-data's
`calendar`, `calendar_year` and `calendar_day`.

Integer IDs internally; every table people look at has a short readable
`name`. Every change here needs a matching Alembic migration
(`tests/test_migrations.py` checks).
"""

from datetime import date, datetime, time
from decimal import Decimal

from sqlalchemy import (
    JSON,
    CheckConstraint,
    Date,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    LargeBinary,
    Numeric,
    SmallInteger,
    String,
    Text,
    Time,
    func,
    text,
)
from sqlalchemy.dialects.postgresql import JSONB
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
    __table_args__ = (
        Index("ix_capture_source_fetched", "source_id", "fetched_at"),
        Index("ix_capture_source_period", "source_id", "period", "id"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    source_id: Mapped[int] = mapped_column(Integer, ForeignKey("source.id"))
    fetched_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    http_status: Mapped[int] = mapped_column(SmallInteger)
    content_type: Mapped[str | None] = mapped_column(String(200))
    sha256: Mapped[str] = mapped_column(String(64))
    size_bytes: Mapped[int] = mapped_column(Integer)
    body: Mapped[bytes] = mapped_column(LargeBinary)
    # For sources fetched a period at a time (Treasury's par curve by month,
    # phase 2 Part B): "2026-10". Dedupe and revisions are per source and
    # period. Empty for sources fetched whole (the calendar pages).
    period: Mapped[str | None] = mapped_column(String(10))


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
    period: Mapped[str | None] = mapped_column(String(10))  # the period fetched, for period sources


class SourceYear(Base):
    """A year a calendar source covers, as of its latest capture listing it (near-raw).

    As in phase 1's calendar_year, a year the source stops listing is kept: dropping
    off a page that rolls forward isn't a change to the calendar.
    """

    __tablename__ = "source_year"

    source_id: Mapped[int] = mapped_column(Integer, ForeignKey("source.id"), primary_key=True)
    year: Mapped[int] = mapped_column(SmallInteger, primary_key=True)
    capture_id: Mapped[int] = mapped_column(Integer, ForeignKey("capture.id"))
    first_seen_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))


class SourceDay(Base):
    """A closed or early-close weekday as one source states it (near-raw), with history.

    One current row per source and date. Two sources listing the same date
    both keep their row: precedence is calendar-svc's job. `valid_from` and
    `valid_to` are the fetch times of the captures that said it and stopped
    saying it, so a rebuild from raw gives the same rows.
    """

    __tablename__ = "source_day"
    __table_args__ = (
        CheckConstraint("status IN ('closed', 'early_close')", name="ck_source_day_status"),
        CheckConstraint("(status = 'early_close') = (close_time IS NOT NULL)", name="ck_source_day_close_time"),
        Index(
            "uq_source_day_current",
            "source_id",
            "day",
            unique=True,
            postgresql_where=text("valid_to IS NULL"),
            sqlite_where=text("valid_to IS NULL"),
        ),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    source_id: Mapped[int] = mapped_column(Integer, ForeignKey("source.id"))
    day: Mapped[date] = mapped_column(Date)
    status: Mapped[str] = mapped_column(String(12))
    close_time: Mapped[time | None] = mapped_column(Time)
    holiday: Mapped[str] = mapped_column(String(100))
    capture_id: Mapped[int] = mapped_column(Integer, ForeignKey("capture.id"))
    valid_from: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    valid_to: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class Observation(Base):
    """A time-series value as one source publishes it (near-raw, phase 2 Part B).

    One row per source, the source's own series key (BC_10YEAR,
    RIFLGFCY10_N.B), date and field, holding the value exactly as printed
    (numeric, in the source's unit: percent for CMT yields). No instruments,
    no conversion: quote-svc maps keys to instruments through secmaster-svc and
    builds golden quotes. History like source_day: within a capture's period
    (its month), a changed value closes the old row (`valid_to`) and adds a
    new one, and a value the source drops is closed off. Times are the
    captures' fetch times, so a rebuild from raw gives the same rows.
    """

    __tablename__ = "observation"
    __table_args__ = (
        Index(
            "uq_observation_current",
            "source_id",
            "source_key",
            "as_of",
            "field",
            unique=True,
            postgresql_where=text("valid_to IS NULL"),
            sqlite_where=text("valid_to IS NULL"),
        ),
        Index("ix_observation_source_period", "source_id", "period"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    source_id: Mapped[int] = mapped_column(Integer, ForeignKey("source.id"))
    period: Mapped[str] = mapped_column(String(10))
    source_key: Mapped[str] = mapped_column(String(40))
    as_of: Mapped[date] = mapped_column(Date)
    field: Mapped[str] = mapped_column(String(20))
    value: Mapped[Decimal] = mapped_column(Numeric)
    unit: Mapped[str] = mapped_column(String(20))
    capture_id: Mapped[int] = mapped_column(Integer, ForeignKey("capture.id"))
    valid_from: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    valid_to: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


# JSONB on Postgres (the hub); plain JSON on SQLite (tests).
JSON_DOC = JSON().with_variant(JSONB(), "postgresql")


class Record(Base):
    """A record as one source publishes it (near-raw, phase 3): what isn't a time series.

    An auction's terms and results (TreasuryDirect, Fiscal Data) or a line of
    the stripped-securities table, keyed by the source's own identity for it
    ("912810UW6/2026-10-15": CUSIP and issue date), with every field exactly
    as printed in `fields`. Nothing typed or renamed; secmaster-svc does that.
    History like observation: within a capture's period, a changed record
    closes the old row (`valid_to`) and adds a new one, and a record the source
    drops is closed off. Times are the captures' fetch times, so a rebuild from
    raw gives the same rows.
    """

    __tablename__ = "record"
    __table_args__ = (
        Index(
            "uq_record_current",
            "source_id",
            "record_type",
            "source_key",
            unique=True,
            postgresql_where=text("valid_to IS NULL"),
            sqlite_where=text("valid_to IS NULL"),
        ),
        Index("ix_record_source_period", "source_id", "period"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    source_id: Mapped[int] = mapped_column(Integer, ForeignKey("source.id"))
    period: Mapped[str] = mapped_column(String(10))
    record_type: Mapped[str] = mapped_column(String(30))
    source_key: Mapped[str] = mapped_column(String(80))
    as_of: Mapped[date] = mapped_column(Date)
    fields: Mapped[dict] = mapped_column(JSON_DOC)
    capture_id: Mapped[int] = mapped_column(Integer, ForeignKey("capture.id"))
    valid_from: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    valid_to: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class RecordComparison(Base):
    """The latest cross-check of two sources' records (docs/phase-3.md, step 5): one row per pair, replaced each run."""

    __tablename__ = "record_comparison"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    left_source: Mapped[str] = mapped_column(String(40))  # TD-SECURITIES
    right_source: Mapped[str] = mapped_column(String(40))  # FD-AUCTIONS
    record_type: Mapped[str] = mapped_column(String(30))
    ran_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    compared: Mapped[int] = mapped_column(Integer)  # records both list
    only_left: Mapped[int] = mapped_column(Integer)
    only_right: Mapped[int] = mapped_column(Integer)
    records_differing: Mapped[int] = mapped_column(Integer)  # records with at least one field that differs
    detail: Mapped[dict] = mapped_column(JSON_DOC)  # per field: counts and examples; keys only in one source
