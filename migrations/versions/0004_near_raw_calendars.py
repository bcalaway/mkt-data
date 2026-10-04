"""Near-raw calendar tables: source_year and source_day (docs/phase-2.md, Part A)

Each calendar source's parse as that source states it, one set of rows per
source and no precedence, for calendar-svc to build golden calendars from.
`calendar_day` and `calendar_year` are untouched; they retire once
calendar-svc takes over. Filled by the rebuild job, which replays every
capture, not by this migration.

Revision ID: 0004
Revises: 0003
Create Date: 2026-10-04
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0004"
down_revision: str | None = "0003"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "source_year",
        sa.Column("source_id", sa.Integer(), sa.ForeignKey("source.id"), primary_key=True),
        sa.Column("year", sa.SmallInteger(), primary_key=True),
        sa.Column("capture_id", sa.Integer(), sa.ForeignKey("capture.id"), nullable=False),
        sa.Column("first_seen_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_table(
        "source_day",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("source_id", sa.Integer(), sa.ForeignKey("source.id"), nullable=False),
        sa.Column("day", sa.Date(), nullable=False),
        sa.Column("status", sa.String(length=12), nullable=False),
        sa.Column("close_time", sa.Time(), nullable=True),
        sa.Column("holiday", sa.String(length=100), nullable=False),
        sa.Column("capture_id", sa.Integer(), sa.ForeignKey("capture.id"), nullable=False),
        sa.Column("valid_from", sa.DateTime(timezone=True), nullable=False),
        sa.Column("valid_to", sa.DateTime(timezone=True), nullable=True),
        sa.CheckConstraint("status IN ('closed', 'early_close')", name="ck_source_day_status"),
        sa.CheckConstraint("(status = 'early_close') = (close_time IS NOT NULL)", name="ck_source_day_close_time"),
    )
    op.create_index(
        "uq_source_day_current",
        "source_day",
        ["source_id", "day"],
        unique=True,
        postgresql_where=sa.text("valid_to IS NULL"),
        sqlite_where=sa.text("valid_to IS NULL"),
    )


def downgrade() -> None:
    op.drop_index("uq_source_day_current", table_name="source_day")
    op.drop_table("source_day")
    op.drop_table("source_year")
