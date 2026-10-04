"""Drop mkt-data's golden calendar: calendar, calendar_year, calendar_day

calendar-svc owns the golden calendars since phase 2, step A5
(docs/phase-2.md). Its calendars matched these tables day for day and year for
year for FED, SIFMA-US and NYSE, 1900-2100 (step A4, 2026-10-04), and
everything that read them now reads calendar-svc. These were processed
tables, rebuildable from raw: the captures and the near-raw rows stay.

The downgrade recreates the empty tables; a reparse would refill them only
with the phase-1 code, which this migration's release removes.

Revision ID: 0005
Revises: 0004
Create Date: 2026-10-04
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0005"
down_revision: str | None = "0004"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.drop_index("uq_calendar_day_current", table_name="calendar_day")
    op.drop_table("calendar_day")
    op.drop_table("calendar_year")
    op.drop_table("calendar")


def downgrade() -> None:
    op.create_table(
        "calendar",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("name", sa.String(length=20), nullable=False, unique=True),
        sa.Column("description", sa.Text(), nullable=False),
        sa.Column("timezone", sa.String(length=40), nullable=False),
    )
    op.create_table(
        "calendar_year",
        sa.Column("calendar_id", sa.Integer(), sa.ForeignKey("calendar.id"), primary_key=True),
        sa.Column("year", sa.SmallInteger(), primary_key=True),
        sa.Column("capture_id", sa.Integer(), sa.ForeignKey("capture.id"), nullable=False),
        sa.Column("first_seen_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )
    op.create_table(
        "calendar_day",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("calendar_id", sa.Integer(), sa.ForeignKey("calendar.id"), nullable=False),
        sa.Column("day", sa.Date(), nullable=False),
        sa.Column("status", sa.String(length=12), nullable=False),
        sa.Column("close_time", sa.Time(), nullable=True),
        sa.Column("holiday", sa.String(length=100), nullable=False),
        sa.Column("capture_id", sa.Integer(), sa.ForeignKey("capture.id"), nullable=False),
        sa.Column("valid_from", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("valid_to", sa.DateTime(timezone=True), nullable=True),
        sa.CheckConstraint("status IN ('closed', 'early_close')", name="ck_calendar_day_status"),
        sa.CheckConstraint("(status = 'early_close') = (close_time IS NOT NULL)", name="ck_calendar_day_close_time"),
    )
    op.create_index(
        "uq_calendar_day_current",
        "calendar_day",
        ["calendar_id", "day"],
        unique=True,
        postgresql_where=sa.text("valid_to IS NULL"),
        sqlite_where=sa.text("valid_to IS NULL"),
    )
