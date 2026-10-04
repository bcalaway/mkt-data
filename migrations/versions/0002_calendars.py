"""calendars: raw capture store and processed calendar tables

Replaces the template's example `items` table with the phase-1 schema
(docs/phase-1.md, step 3). On Postgres, `capture` also gets a trigger that
refuses UPDATE, DELETE and TRUNCATE: raw data is append-only and kept
forever. (SQLite, used only by tests/test_migrations.py, has no triggers
of that kind and doesn't need them.)

Revision ID: 0002
Revises: 0001
Create Date: 2026-10-03
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0002"
down_revision: str | None = "0001"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.drop_table("items")

    op.create_table(
        "source",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("name", sa.String(length=40), nullable=False, unique=True),
        sa.Column("url", sa.Text(), nullable=False),
        sa.Column("description", sa.Text(), nullable=False),
    )
    op.create_table(
        "capture",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("source_id", sa.Integer(), sa.ForeignKey("source.id"), nullable=False),
        sa.Column("fetched_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("http_status", sa.SmallInteger(), nullable=False),
        sa.Column("content_type", sa.String(length=200), nullable=True),
        sa.Column("sha256", sa.String(length=64), nullable=False),
        sa.Column("size_bytes", sa.Integer(), nullable=False),
        sa.Column("body", sa.LargeBinary(), nullable=False),
    )
    op.create_index("ix_capture_source_fetched", "capture", ["source_id", "fetched_at"])
    op.create_table(
        "source_check",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("source_id", sa.Integer(), sa.ForeignKey("source.id"), nullable=False),
        sa.Column("checked_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("outcome", sa.String(length=12), nullable=False),
        sa.Column("capture_id", sa.Integer(), sa.ForeignKey("capture.id"), nullable=True),
        sa.Column("detail", sa.Text(), nullable=True),
        sa.CheckConstraint("outcome IN ('new', 'unchanged', 'error')", name="ck_source_check_outcome"),
    )
    op.create_index("ix_source_check_source_checked", "source_check", ["source_id", "checked_at"])
    op.create_table(
        "calendar",
        sa.Column("id", sa.SmallInteger(), primary_key=True),
        sa.Column("name", sa.String(length=20), nullable=False, unique=True),
        sa.Column("description", sa.Text(), nullable=False),
        sa.Column("timezone", sa.String(length=40), nullable=False),
    )
    op.create_table(
        "calendar_year",
        sa.Column("calendar_id", sa.SmallInteger(), sa.ForeignKey("calendar.id"), primary_key=True),
        sa.Column("year", sa.SmallInteger(), primary_key=True),
        sa.Column("capture_id", sa.Integer(), sa.ForeignKey("capture.id"), nullable=False),
        sa.Column("first_seen_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )
    op.create_table(
        "calendar_day",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("calendar_id", sa.SmallInteger(), sa.ForeignKey("calendar.id"), nullable=False),
        sa.Column("day", sa.Date(), nullable=False),
        sa.Column("status", sa.String(length=12), nullable=False),
        sa.Column("close_time", sa.Time(), nullable=True),
        sa.Column("holiday", sa.String(length=100), nullable=False),
        sa.Column("capture_id", sa.Integer(), sa.ForeignKey("capture.id"), nullable=False),
        sa.Column("valid_from", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("valid_to", sa.DateTime(timezone=True), nullable=True),
        sa.CheckConstraint("status IN ('closed', 'early_close')", name="ck_calendar_day_status"),
        sa.CheckConstraint(
            "(status = 'early_close') = (close_time IS NOT NULL)", name="ck_calendar_day_close_time"
        ),
    )
    op.create_index(
        "uq_calendar_day_current",
        "calendar_day",
        ["calendar_id", "day"],
        unique=True,
        postgresql_where=sa.text("valid_to IS NULL"),
        sqlite_where=sa.text("valid_to IS NULL"),
    )

    if op.get_bind().dialect.name == "postgresql":
        op.execute(
            """
            CREATE FUNCTION capture_append_only() RETURNS trigger LANGUAGE plpgsql AS $$
            BEGIN
              RAISE EXCEPTION 'capture is append-only: raw data is never updated or deleted';
            END $$;
            """
        )
        op.execute(
            "CREATE TRIGGER capture_no_update_delete BEFORE UPDATE OR DELETE ON capture "
            "FOR EACH ROW EXECUTE FUNCTION capture_append_only()"
        )
        op.execute(
            "CREATE TRIGGER capture_no_truncate BEFORE TRUNCATE ON capture "
            "FOR EACH STATEMENT EXECUTE FUNCTION capture_append_only()"
        )


def downgrade() -> None:
    # Drops raw data too. Only for a database with nothing worth keeping
    # (tests, a fresh dev copy); never run against production.
    if op.get_bind().dialect.name == "postgresql":
        op.execute("DROP TRIGGER IF EXISTS capture_no_truncate ON capture")
        op.execute("DROP TRIGGER IF EXISTS capture_no_update_delete ON capture")
        op.execute("DROP FUNCTION IF EXISTS capture_append_only()")
    op.drop_index("uq_calendar_day_current", table_name="calendar_day")
    op.drop_table("calendar_day")
    op.drop_table("calendar_year")
    op.drop_table("calendar")
    op.drop_index("ix_source_check_source_checked", table_name="source_check")
    op.drop_table("source_check")
    op.drop_index("ix_capture_source_fetched", table_name="capture")
    op.drop_table("capture")
    op.drop_table("source")
    op.create_table(
        "items",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("name", sa.String(length=200), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )
