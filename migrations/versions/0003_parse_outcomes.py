"""source_check: record each parse's outcome, and reparses

Every capture job and every reparse now records whether the parse worked
(`parse_outcome` 'ok' or 'error', with the error in `parse_detail`), so the
metrics can report a failing parser without inferring it. A reparse is a
check with outcome 'reparse' (no fetch) pointing at the capture it re-read.
Sources with no parser leave `parse_outcome` empty.

Batch mode so SQLite (tests) can change the CHECK constraint; on Postgres
it's plain ALTERs.

Revision ID: 0003
Revises: 0002
Create Date: 2026-10-04
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0003"
down_revision: str | None = "0002"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    with op.batch_alter_table("source_check") as batch:
        batch.add_column(sa.Column("parse_outcome", sa.String(length=8), nullable=True))
        batch.add_column(sa.Column("parse_detail", sa.Text(), nullable=True))
        batch.drop_constraint("ck_source_check_outcome", type_="check")
        batch.create_check_constraint(
            "ck_source_check_outcome", "outcome IN ('new', 'unchanged', 'error', 'reparse')"
        )
        batch.create_check_constraint("ck_source_check_parse_outcome", "parse_outcome IN ('ok', 'error')")


def downgrade() -> None:
    op.execute("DELETE FROM source_check WHERE outcome = 'reparse'")
    with op.batch_alter_table("source_check") as batch:
        batch.drop_constraint("ck_source_check_parse_outcome", type_="check")
        batch.drop_constraint("ck_source_check_outcome", type_="check")
        batch.create_check_constraint("ck_source_check_outcome", "outcome IN ('new', 'unchanged', 'error')")
        batch.drop_column("parse_detail")
        batch.drop_column("parse_outcome")
