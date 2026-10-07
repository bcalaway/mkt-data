"""record_comparison: the latest cross-check of two sources' records

Phase 3, step 5 (docs/phase-3.md): TreasuryDirect's auction records against
Fiscal Data's. One row per pair of sources, replaced each run.

Revision ID: 0009
Revises: 0008
Create Date: 2026-10-07
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0009"
down_revision: str | None = "0008"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "record_comparison",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("left_source", sa.String(length=40), nullable=False),
        sa.Column("right_source", sa.String(length=40), nullable=False),
        sa.Column("record_type", sa.String(length=30), nullable=False),
        sa.Column("ran_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("compared", sa.Integer(), nullable=False),
        sa.Column("only_left", sa.Integer(), nullable=False),
        sa.Column("only_right", sa.Integer(), nullable=False),
        sa.Column("records_differing", sa.Integer(), nullable=False),
        sa.Column("detail", sa.JSON().with_variant(postgresql.JSONB(), "postgresql"), nullable=False),
    )


def downgrade() -> None:
    op.drop_table("record_comparison")
