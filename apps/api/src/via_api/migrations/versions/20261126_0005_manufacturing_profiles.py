"""manufacturing profiles

Revision ID: 0005
Revises: 0004
Create Date: 2026-11-26 07:46:06.763472+00:00
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0005"
down_revision: str | None = "0004"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "manufacturing_profiles",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("project_id", sa.Uuid(), nullable=False),
        sa.Column("name", sa.String(length=100), nullable=False),
        sa.Column("description", sa.Text(), server_default="", nullable=False),
        sa.Column("values", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("created_by_id", sa.Uuid(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.ForeignKeyConstraint(
            ["created_by_id"],
            ["users.id"],
            name=op.f("fk_manufacturing_profiles_created_by_id_users"),
            ondelete="SET NULL",
        ),
        sa.ForeignKeyConstraint(
            ["project_id"],
            ["projects.id"],
            name=op.f("fk_manufacturing_profiles_project_id_projects"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_manufacturing_profiles")),
        sa.UniqueConstraint("project_id", "name", name=op.f("uq_manufacturing_profiles_project_id_name")),
    )
    op.create_index(
        op.f("ix_manufacturing_profiles_project_id"), "manufacturing_profiles", ["project_id"], unique=False
    )


def downgrade() -> None:
    op.drop_index(op.f("ix_manufacturing_profiles_project_id"), table_name="manufacturing_profiles")
    op.drop_table("manufacturing_profiles")
