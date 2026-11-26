"""change sets and lineage

Revision ID: 0008
Revises: 0007
Create Date: 2026-11-26 08:39:15.317232+00:00
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0008"
down_revision: str | None = "0007"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.drop_constraint(op.f("ck_analysis_runs_analysis_kind"), "analysis_runs", type_="check")
    op.create_check_constraint(
        "analysis_kind", "analysis_runs", "kind IN ('pcb_import', 'pcb_analysis', 'pcb_optimization', 'pcb_export')"
    )
    op.create_table(
        "change_sets",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("project_id", sa.Uuid(), nullable=False),
        sa.Column("design_id", sa.Uuid(), nullable=False),
        sa.Column("base_revision_id", sa.Uuid(), nullable=False),
        sa.Column("result_revision_id", sa.Uuid(), nullable=True),
        sa.Column("export_run_id", sa.Uuid(), nullable=True),
        sa.Column("title", sa.String(length=200), nullable=False),
        sa.Column(
            "status",
            sa.Enum(
                "draft",
                "applying",
                "applied",
                "failed",
                "rolled_back",
                name="change_set_status",
                native_enum=False,
                create_constraint=True,
                length=32,
            ),
            server_default="draft",
            nullable=False,
        ),
        sa.Column("result", postgresql.JSONB(astext_type=sa.Text()), server_default="{}", nullable=False),
        sa.Column("error_code", sa.String(length=64), nullable=True),
        sa.Column("error_message", sa.Text(), nullable=True),
        sa.Column("created_by_id", sa.Uuid(), nullable=True),
        sa.Column("applied_by_id", sa.Uuid(), nullable=True),
        sa.Column("applied_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("rolled_back_by_id", sa.Uuid(), nullable=True),
        sa.Column("rolled_back_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.ForeignKeyConstraint(
            ["applied_by_id"], ["users.id"], name=op.f("fk_change_sets_applied_by_id_users"), ondelete="SET NULL"
        ),
        sa.ForeignKeyConstraint(
            ["base_revision_id"],
            ["design_revisions.id"],
            name=op.f("fk_change_sets_base_revision_id_design_revisions"),
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["created_by_id"], ["users.id"], name=op.f("fk_change_sets_created_by_id_users"), ondelete="SET NULL"
        ),
        sa.ForeignKeyConstraint(
            ["design_id"], ["designs.id"], name=op.f("fk_change_sets_design_id_designs"), ondelete="CASCADE"
        ),
        sa.ForeignKeyConstraint(
            ["export_run_id"],
            ["analysis_runs.id"],
            name=op.f("fk_change_sets_export_run_id_analysis_runs"),
            ondelete="SET NULL",
        ),
        sa.ForeignKeyConstraint(
            ["project_id"], ["projects.id"], name=op.f("fk_change_sets_project_id_projects"), ondelete="CASCADE"
        ),
        sa.ForeignKeyConstraint(
            ["result_revision_id"],
            ["design_revisions.id"],
            name=op.f("fk_change_sets_result_revision_id_design_revisions"),
            ondelete="SET NULL",
        ),
        sa.ForeignKeyConstraint(
            ["rolled_back_by_id"],
            ["users.id"],
            name=op.f("fk_change_sets_rolled_back_by_id_users"),
            ondelete="SET NULL",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_change_sets")),
    )
    op.create_index(op.f("ix_change_sets_design_id"), "change_sets", ["design_id"], unique=False)
    op.create_index(op.f("ix_change_sets_project_id"), "change_sets", ["project_id"], unique=False)
    op.add_column("design_changes", sa.Column("change_set_id", sa.Uuid(), nullable=True))
    op.add_column("design_changes", sa.Column("origin_candidate_id", sa.Uuid(), nullable=True))
    op.add_column(
        "design_changes",
        sa.Column(
            "status",
            sa.Enum(
                "proposed",
                "applied",
                "refused",
                name="change_status",
                native_enum=False,
                create_constraint=True,
                length=32,
            ),
            server_default="proposed",
            nullable=False,
        ),
    )
    op.add_column("design_changes", sa.Column("status_reason", sa.Text(), nullable=True))
    op.create_index(op.f("ix_design_changes_change_set_id"), "design_changes", ["change_set_id"], unique=False)
    op.create_unique_constraint(
        op.f("uq_design_changes_change_set_id_ordinal"), "design_changes", ["change_set_id", "ordinal"]
    )
    op.create_foreign_key(
        op.f("fk_design_changes_change_set_id_change_sets"),
        "design_changes",
        "change_sets",
        ["change_set_id"],
        ["id"],
        ondelete="CASCADE",
    )
    op.create_foreign_key(
        op.f("fk_design_changes_origin_candidate_id_optimization_candidates"),
        "design_changes",
        "optimization_candidates",
        ["origin_candidate_id"],
        ["id"],
        ondelete="SET NULL",
    )
    op.create_check_constraint("one_owner", "design_changes", "(candidate_id IS NULL) <> (change_set_id IS NULL)")
    op.add_column("design_revisions", sa.Column("parent_revision_id", sa.Uuid(), nullable=True))
    op.create_foreign_key(
        op.f("fk_design_revisions_parent_revision_id_design_revisions"),
        "design_revisions",
        "design_revisions",
        ["parent_revision_id"],
        ["id"],
        ondelete="SET NULL",
    )


def downgrade() -> None:
    op.execute("DELETE FROM analysis_runs WHERE kind = 'pcb_export'")
    op.drop_constraint(op.f("ck_analysis_runs_analysis_kind"), "analysis_runs", type_="check")
    op.create_check_constraint(
        "analysis_kind", "analysis_runs", "kind IN ('pcb_import', 'pcb_analysis', 'pcb_optimization')"
    )
    op.drop_constraint(op.f("ck_design_changes_one_owner"), "design_changes", type_="check")
    op.drop_constraint(
        op.f("fk_design_revisions_parent_revision_id_design_revisions"), "design_revisions", type_="foreignkey"
    )
    op.drop_column("design_revisions", "parent_revision_id")
    op.drop_constraint(
        op.f("fk_design_changes_origin_candidate_id_optimization_candidates"), "design_changes", type_="foreignkey"
    )
    op.drop_constraint(op.f("fk_design_changes_change_set_id_change_sets"), "design_changes", type_="foreignkey")
    op.drop_constraint(op.f("uq_design_changes_change_set_id_ordinal"), "design_changes", type_="unique")
    op.drop_index(op.f("ix_design_changes_change_set_id"), table_name="design_changes")
    op.drop_column("design_changes", "status_reason")
    op.drop_column("design_changes", "status")
    op.drop_column("design_changes", "origin_candidate_id")
    op.drop_column("design_changes", "change_set_id")
    op.drop_index(op.f("ix_change_sets_project_id"), table_name="change_sets")
    op.drop_index(op.f("ix_change_sets_design_id"), table_name="change_sets")
    op.drop_table("change_sets")
