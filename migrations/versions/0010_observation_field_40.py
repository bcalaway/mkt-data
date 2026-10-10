"""observation.field: 40 characters, for the CFTC's column names

Phase 4, step 5 (docs/phase-4.md): the Traders in Financial Futures report's columns are
kept under the CFTC's own names, as the other sources' are, and the longest
(`dealer_positions_spread_all`, `conc_net_le_8_tdr_short_all`) are 27 characters.
Widening a varchar is a catalog change on Postgres: no table rewrite.

Revision ID: 0010
Revises: 0009
Create Date: 2026-10-10
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0010"
down_revision: str | None = "0009"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    with op.batch_alter_table("observation") as b:
        b.alter_column("field", existing_type=sa.String(length=20), type_=sa.String(length=40),
                       existing_nullable=False)


def downgrade() -> None:
    with op.batch_alter_table("observation") as b:
        b.alter_column("field", existing_type=sa.String(length=40), type_=sa.String(length=20),
                       existing_nullable=False)
