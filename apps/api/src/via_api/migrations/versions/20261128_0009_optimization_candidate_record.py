"""optimization candidate record: warnings, limitations, execution, score, hash

Revision ID: 0009
Revises: 0008
Create Date: 2026-11-28 09:00:00.000000+00:00
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
    for name, default in (("warnings", "[]"), ("limitations", "[]"), ("execution", "{}")):
        op.add_column(
            "optimization_candidates",
            sa.Column(name, postgresql.JSONB(astext_type=sa.Text()), server_default=default, nullable=False),
        )
    op.add_column("optimization_candidates", sa.Column("score", postgresql.JSONB(astext_type=sa.Text()), nullable=True))
    op.add_column(
        "optimization_candidates", sa.Column("candidate_hash", sa.String(length=64), server_default="", nullable=False)
    )


def downgrade() -> None:
    for name in ("candidate_hash", "score", "execution", "limitations", "warnings"):
        op.drop_column("optimization_candidates", name)
