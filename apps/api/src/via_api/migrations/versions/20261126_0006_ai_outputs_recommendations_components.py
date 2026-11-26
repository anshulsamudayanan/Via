"""ai outputs recommendations components

Revision ID: 0006
Revises: 0005
Create Date: 2026-11-26 08:04:19.430162+00:00
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0006"
down_revision: str | None = "0005"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "component_records",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("project_id", sa.Uuid(), nullable=False),
        sa.Column("manufacturer", sa.String(length=200), nullable=False),
        sa.Column("part_number", sa.String(length=200), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("package", sa.String(length=200), nullable=True),
        sa.Column("specs", postgresql.JSONB(astext_type=sa.Text()), server_default="[]", nullable=False),
        sa.Column("datasheets", postgresql.JSONB(astext_type=sa.Text()), server_default="[]", nullable=False),
        sa.Column("source", sa.String(length=200), nullable=False),
        sa.Column("verification", sa.String(length=16), server_default="unverified", nullable=False),
        sa.Column("created_by_id", sa.Uuid(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.ForeignKeyConstraint(
            ["created_by_id"], ["users.id"], name=op.f("fk_component_records_created_by_id_users"), ondelete="SET NULL"
        ),
        sa.ForeignKeyConstraint(
            ["project_id"], ["projects.id"], name=op.f("fk_component_records_project_id_projects"), ondelete="CASCADE"
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_component_records")),
        sa.UniqueConstraint(
            "project_id",
            "manufacturer",
            "part_number",
            name=op.f("uq_component_records_project_id_manufacturer_part_number"),
        ),
    )
    op.create_index(op.f("ix_component_records_project_id"), "component_records", ["project_id"], unique=False)
    op.create_table(
        "ai_outputs",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("project_id", sa.Uuid(), nullable=False),
        sa.Column("design_id", sa.Uuid(), nullable=False),
        sa.Column("revision_id", sa.Uuid(), nullable=False),
        sa.Column("analysis_run_id", sa.Uuid(), nullable=True),
        sa.Column("kind", sa.String(length=32), nullable=False),
        sa.Column("question", sa.Text(), nullable=True),
        sa.Column("focus", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("provider", sa.String(length=64), nullable=False),
        sa.Column("model", sa.String(length=128), nullable=False),
        sa.Column("prompt_version", sa.String(length=32), nullable=False),
        sa.Column("context_sha256", sa.String(length=64), nullable=False),
        sa.Column("output", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("accepted", sa.Boolean(), nullable=False),
        sa.Column("verification", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("input_tokens", sa.Integer(), server_default="0", nullable=False),
        sa.Column("output_tokens", sa.Integer(), server_default="0", nullable=False),
        sa.Column("created_by_id", sa.Uuid(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.ForeignKeyConstraint(
            ["analysis_run_id"],
            ["analysis_runs.id"],
            name=op.f("fk_ai_outputs_analysis_run_id_analysis_runs"),
            ondelete="SET NULL",
        ),
        sa.ForeignKeyConstraint(
            ["created_by_id"], ["users.id"], name=op.f("fk_ai_outputs_created_by_id_users"), ondelete="SET NULL"
        ),
        sa.ForeignKeyConstraint(
            ["design_id"], ["designs.id"], name=op.f("fk_ai_outputs_design_id_designs"), ondelete="CASCADE"
        ),
        sa.ForeignKeyConstraint(
            ["project_id"], ["projects.id"], name=op.f("fk_ai_outputs_project_id_projects"), ondelete="CASCADE"
        ),
        sa.ForeignKeyConstraint(
            ["revision_id"],
            ["design_revisions.id"],
            name=op.f("fk_ai_outputs_revision_id_design_revisions"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_ai_outputs")),
    )
    op.create_index(op.f("ix_ai_outputs_project_id"), "ai_outputs", ["project_id"], unique=False)
    op.create_table(
        "recommendations",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("ai_output_id", sa.Uuid(), nullable=False),
        sa.Column("project_id", sa.Uuid(), nullable=False),
        sa.Column("design_id", sa.Uuid(), nullable=False),
        sa.Column("revision_id", sa.Uuid(), nullable=False),
        sa.Column("problem", sa.Text(), nullable=False),
        sa.Column("proposed_change", sa.Text(), nullable=False),
        sa.Column("rationale", sa.Text(), nullable=False),
        sa.Column("details", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("evidence_finding_ids", postgresql.ARRAY(sa.String(length=64)), server_default="{}", nullable=False),
        sa.Column("confidence", sa.String(length=16), nullable=False),
        sa.Column("status", sa.String(length=16), server_default="open", nullable=False),
        sa.Column("status_reason", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.ForeignKeyConstraint(
            ["ai_output_id"],
            ["ai_outputs.id"],
            name=op.f("fk_recommendations_ai_output_id_ai_outputs"),
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["design_id"], ["designs.id"], name=op.f("fk_recommendations_design_id_designs"), ondelete="CASCADE"
        ),
        sa.ForeignKeyConstraint(
            ["project_id"], ["projects.id"], name=op.f("fk_recommendations_project_id_projects"), ondelete="CASCADE"
        ),
        sa.ForeignKeyConstraint(
            ["revision_id"],
            ["design_revisions.id"],
            name=op.f("fk_recommendations_revision_id_design_revisions"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_recommendations")),
    )
    op.create_index(op.f("ix_recommendations_ai_output_id"), "recommendations", ["ai_output_id"], unique=False)
    op.create_index(op.f("ix_recommendations_design_id"), "recommendations", ["design_id"], unique=False)
    op.create_index(op.f("ix_recommendations_project_id"), "recommendations", ["project_id"], unique=False)


def downgrade() -> None:
    op.drop_index(op.f("ix_recommendations_project_id"), table_name="recommendations")
    op.drop_index(op.f("ix_recommendations_design_id"), table_name="recommendations")
    op.drop_index(op.f("ix_recommendations_ai_output_id"), table_name="recommendations")
    op.drop_table("recommendations")
    op.drop_index(op.f("ix_ai_outputs_project_id"), table_name="ai_outputs")
    op.drop_table("ai_outputs")
    op.drop_index(op.f("ix_component_records_project_id"), table_name="component_records")
    op.drop_table("component_records")
