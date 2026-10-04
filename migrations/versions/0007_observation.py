"""observation: near-raw time-series values, as each source publishes them

Phase 2, Part B step 2 (docs/phase-2.md): Treasury's par yield curve and the
Fed's H.15 parsed into one generic table, values as printed with their unit,
history per source, series key, date and field.

Revision ID: 0007
Revises: 0006
Create Date: 2026-10-04
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0007"
down_revision: str | None = "0006"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "observation",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("source_id", sa.Integer(), sa.ForeignKey("source.id"), nullable=False),
        sa.Column("period", sa.String(length=10), nullable=False),
        sa.Column("source_key", sa.String(length=40), nullable=False),
        sa.Column("as_of", sa.Date(), nullable=False),
        sa.Column("field", sa.String(length=20), nullable=False),
        sa.Column("value", sa.Numeric(), nullable=False),
        sa.Column("unit", sa.String(length=20), nullable=False),
        sa.Column("capture_id", sa.Integer(), sa.ForeignKey("capture.id"), nullable=False),
        sa.Column("valid_from", sa.DateTime(timezone=True), nullable=False),
        sa.Column("valid_to", sa.DateTime(timezone=True), nullable=True),
    )
    op.create_index(
        "uq_observation_current",
        "observation",
        ["source_id", "source_key", "as_of", "field"],
        unique=True,
        postgresql_where=sa.text("valid_to IS NULL"),
        sqlite_where=sa.text("valid_to IS NULL"),
    )
    op.create_index("ix_observation_source_period", "observation", ["source_id", "period"])


def downgrade() -> None:
    op.drop_index("ix_observation_source_period", table_name="observation")
    op.drop_index("uq_observation_current", table_name="observation")
    op.drop_table("observation")
