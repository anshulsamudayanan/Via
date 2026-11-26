"""job lifecycle

Revision ID: 0003
Revises: 0002
Create Date: 2026-11-26 05:22:51.897079+00:00
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0003"
down_revision: str | None = "0002"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column("analysis_runs", sa.Column("attempt", sa.Integer(), server_default="0", nullable=False))
    op.add_column("analysis_runs", sa.Column("job_id", sa.String(length=128), nullable=True))
    op.add_column("analysis_runs", sa.Column("heartbeat_at", sa.DateTime(timezone=True), nullable=True))
    op.create_index("ix_analysis_runs_kind_status", "analysis_runs", ["kind", "status"], unique=False)


def downgrade() -> None:
    op.drop_index("ix_analysis_runs_kind_status", table_name="analysis_runs")
    op.drop_column("analysis_runs", "heartbeat_at")
    op.drop_column("analysis_runs", "job_id")
    op.drop_column("analysis_runs", "attempt")
