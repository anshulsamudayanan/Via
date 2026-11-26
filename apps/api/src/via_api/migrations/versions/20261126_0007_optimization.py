"""optimization

Revision ID: 0007
Revises: 0006
Create Date: 2026-11-26 08:18:24.247825+00:00
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0007"
down_revision: str | None = "0006"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.drop_constraint(op.f("ck_analysis_runs_analysis_kind"), "analysis_runs", type_="check")
    op.create_check_constraint(
        "analysis_kind", "analysis_runs", "kind IN ('pcb_import', 'pcb_analysis', 'pcb_optimization')"
    )
    op.create_table(
        "optimization_candidates",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("run_id", sa.Uuid(), nullable=False),
        sa.Column("project_id", sa.Uuid(), nullable=False),
        sa.Column("design_id", sa.Uuid(), nullable=False),
        sa.Column("revision_id", sa.Uuid(), nullable=False),
        sa.Column("key", sa.String(length=64), nullable=False),
        sa.Column("algorithm", sa.String(length=64), nullable=False),
        sa.Column("algorithm_version", sa.String(length=32), nullable=False),
        sa.Column("objectives", postgresql.ARRAY(sa.String(length=32)), nullable=False),
        sa.Column("title", sa.String(length=300), nullable=False),
        sa.Column("summary", sa.Text(), nullable=False),
        sa.Column("metrics_before", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("metrics_after", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("expected_benefits", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("trade_offs", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("validation", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("pareto", sa.Boolean(), server_default="false", nullable=False),
        sa.Column("status", sa.String(length=32), nullable=False),
        sa.Column("status_reason", sa.Text(), nullable=True),
        sa.Column("decided_by_id", sa.Uuid(), nullable=True),
        sa.Column("decided_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("details", postgresql.JSONB(astext_type=sa.Text()), server_default="{}", nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.ForeignKeyConstraint(
            ["decided_by_id"],
            ["users.id"],
            name=op.f("fk_optimization_candidates_decided_by_id_users"),
            ondelete="SET NULL",
        ),
        sa.ForeignKeyConstraint(
            ["design_id"], ["designs.id"], name=op.f("fk_optimization_candidates_design_id_designs"), ondelete="CASCADE"
        ),
        sa.ForeignKeyConstraint(
            ["project_id"],
            ["projects.id"],
            name=op.f("fk_optimization_candidates_project_id_projects"),
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["revision_id"],
            ["design_revisions.id"],
            name=op.f("fk_optimization_candidates_revision_id_design_revisions"),
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["run_id"],
            ["analysis_runs.id"],
            name=op.f("fk_optimization_candidates_run_id_analysis_runs"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_optimization_candidates")),
        sa.UniqueConstraint("run_id", "key", name=op.f("uq_optimization_candidates_run_id_key")),
    )
    op.create_index(
        op.f("ix_optimization_candidates_design_id"), "optimization_candidates", ["design_id"], unique=False
    )
    op.create_index(
        op.f("ix_optimization_candidates_project_id"), "optimization_candidates", ["project_id"], unique=False
    )
    op.create_index(op.f("ix_optimization_candidates_run_id"), "optimization_candidates", ["run_id"], unique=False)
    op.create_table(
        "design_changes",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("candidate_id", sa.Uuid(), nullable=True),
        sa.Column("project_id", sa.Uuid(), nullable=False),
        sa.Column("design_id", sa.Uuid(), nullable=False),
        sa.Column("revision_id", sa.Uuid(), nullable=False),
        sa.Column("ordinal", sa.Integer(), nullable=False),
        sa.Column("kind", sa.String(length=32), nullable=False),
        sa.Column("target", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("before", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("after", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("reason", sa.Text(), nullable=False),
        sa.Column("source", sa.String(length=32), nullable=False),
        sa.Column("finding_ids", postgresql.ARRAY(sa.String(length=64)), server_default="{}", nullable=False),
        sa.Column("exportable", sa.Boolean(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.ForeignKeyConstraint(
            ["candidate_id"],
            ["optimization_candidates.id"],
            name=op.f("fk_design_changes_candidate_id_optimization_candidates"),
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["design_id"], ["designs.id"], name=op.f("fk_design_changes_design_id_designs"), ondelete="CASCADE"
        ),
        sa.ForeignKeyConstraint(
            ["project_id"], ["projects.id"], name=op.f("fk_design_changes_project_id_projects"), ondelete="CASCADE"
        ),
        sa.ForeignKeyConstraint(
            ["revision_id"],
            ["design_revisions.id"],
            name=op.f("fk_design_changes_revision_id_design_revisions"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_design_changes")),
        sa.UniqueConstraint("candidate_id", "ordinal", name=op.f("uq_design_changes_candidate_id_ordinal")),
    )
    op.create_index(op.f("ix_design_changes_candidate_id"), "design_changes", ["candidate_id"], unique=False)
    op.create_index(op.f("ix_design_changes_design_id"), "design_changes", ["design_id"], unique=False)
    op.create_index(op.f("ix_design_changes_project_id"), "design_changes", ["project_id"], unique=False)


def downgrade() -> None:
    op.execute("DELETE FROM analysis_runs WHERE kind = 'pcb_optimization'")
    op.drop_constraint(op.f("ck_analysis_runs_analysis_kind"), "analysis_runs", type_="check")
    op.create_check_constraint("analysis_kind", "analysis_runs", "kind IN ('pcb_import', 'pcb_analysis')")
    op.drop_index(op.f("ix_design_changes_project_id"), table_name="design_changes")
    op.drop_index(op.f("ix_design_changes_design_id"), table_name="design_changes")
    op.drop_index(op.f("ix_design_changes_candidate_id"), table_name="design_changes")
    op.drop_table("design_changes")
    op.drop_index(op.f("ix_optimization_candidates_run_id"), table_name="optimization_candidates")
    op.drop_index(op.f("ix_optimization_candidates_project_id"), table_name="optimization_candidates")
    op.drop_index(op.f("ix_optimization_candidates_design_id"), table_name="optimization_candidates")
    op.drop_table("optimization_candidates")
