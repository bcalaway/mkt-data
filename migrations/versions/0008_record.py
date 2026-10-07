"""record: near-raw records (auctions, stripped securities), as each source publishes them

Phase 3, step 2 (docs/phase-3.md): what isn't a time series (an auction's
terms and results, a line of the stripped-securities table) kept per source,
type and the source's own key, every field as printed, with history like
observation. Prices and CPI use observation.

Revision ID: 0008
Revises: 0007
Create Date: 2026-10-06
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0008"
down_revision: str | None = "0007"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "record",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("source_id", sa.Integer(), sa.ForeignKey("source.id"), nullable=False),
        sa.Column("period", sa.String(length=10), nullable=False),
        sa.Column("record_type", sa.String(length=30), nullable=False),
        sa.Column("source_key", sa.String(length=80), nullable=False),
        sa.Column("as_of", sa.Date(), nullable=False),
        sa.Column("fields", sa.JSON().with_variant(postgresql.JSONB(), "postgresql"), nullable=False),
        sa.Column("capture_id", sa.Integer(), sa.ForeignKey("capture.id"), nullable=False),
        sa.Column("valid_from", sa.DateTime(timezone=True), nullable=False),
        sa.Column("valid_to", sa.DateTime(timezone=True), nullable=True),
    )
    op.create_index(
        "uq_record_current",
        "record",
        ["source_id", "record_type", "source_key"],
        unique=True,
        postgresql_where=sa.text("valid_to IS NULL"),
        sqlite_where=sa.text("valid_to IS NULL"),
    )
    op.create_index("ix_record_source_period", "record", ["source_id", "period"])


def downgrade() -> None:
    op.drop_index("ix_record_source_period", table_name="record")
    op.drop_index("uq_record_current", table_name="record")
    op.drop_table("record")
