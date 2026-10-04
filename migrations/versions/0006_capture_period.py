"""capture.period and source_check.period: sources fetched a period at a time

Phase 2, Part B step 1 (docs/phase-2.md): Treasury's par yield curve and the
Fed's H.15 are fetched a month at a time, so a capture belongs to a period
("2026-10") and dedupe and revisions are per source and period. Existing
captures (the calendar pages, fetched whole) keep an empty period.

Revision ID: 0006
Revises: 0005
Create Date: 2026-10-04
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0006"
down_revision: str | None = "0005"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # capture is append-only on Postgres (a trigger refuses UPDATE), but adding
    # a nullable column rewrites no rows, so the trigger never fires.
    op.add_column("capture", sa.Column("period", sa.String(length=10), nullable=True))
    op.create_index("ix_capture_source_period", "capture", ["source_id", "period", "id"])
    op.add_column("source_check", sa.Column("period", sa.String(length=10), nullable=True))


def downgrade() -> None:
    with op.batch_alter_table("source_check") as batch:
        batch.drop_column("period")
    op.drop_index("ix_capture_source_period", table_name="capture")
    with op.batch_alter_table("capture") as batch:
        batch.drop_column("period")
