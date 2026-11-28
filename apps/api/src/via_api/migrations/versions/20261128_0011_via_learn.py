"""VIA Learn: recommendation feedback, collective knowledge store, retrieval log, reviewer flag

Revision ID: 0011
Revises: 0010
Create Date: 2026-11-28 08:39:03.599391+00:00
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0011"
down_revision: str | None = "0010"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "learn_entries",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("contributor_id", sa.Uuid(), nullable=True),
        sa.Column("consent_id", sa.Uuid(), nullable=True),
        sa.Column(
            "origin",
            sa.Enum(
                "project_derived",
                "free_text",
                name="learn_origin",
                native_enum=False,
                create_constraint=True,
                length=32,
            ),
            nullable=False,
        ),
        sa.Column(
            "status",
            sa.Enum(
                "draft",
                "pending_review",
                "approved",
                "rejected",
                "withdrawn",
                name="learn_status",
                native_enum=False,
                create_constraint=True,
                length=32,
            ),
            nullable=False,
        ),
        sa.Column(
            "category",
            sa.Enum(
                "pcb_design_pattern",
                "component_selection",
                "routing_practice",
                "thermal_design",
                "signal_integrity",
                "manufacturing_constraint",
                "bom_cost_insight",
                "optimization_example",
                "verified_recommendation",
                name="learn_category",
                native_enum=False,
                create_constraint=True,
                length=32,
            ),
            nullable=False,
        ),
        sa.Column("title", sa.String(length=200), nullable=False),
        sa.Column("description", sa.Text(), nullable=False),
        sa.Column("technical_metadata", postgresql.JSONB(astext_type=sa.Text()), server_default="{}", nullable=False),
        sa.Column("source", sa.Text(), nullable=False),
        sa.Column("provenance", postgresql.JSONB(astext_type=sa.Text()), server_default="{}", nullable=False),
        sa.Column(
            "verification_status",
            sa.Enum(
                "unverified",
                "reviewed",
                "verified",
                name="learn_verification",
                native_enum=False,
                create_constraint=True,
                length=32,
            ),
            server_default="unverified",
            nullable=False,
        ),
        sa.Column("verification_basis", sa.Text(), nullable=True),
        sa.Column("permissions", postgresql.JSONB(astext_type=sa.Text()), server_default="{}", nullable=False),
        sa.Column("version", sa.Integer(), server_default="1", nullable=False),
        sa.Column("submitted_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("reviewer_id", sa.Uuid(), nullable=True),
        sa.Column("reviewed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("review_note", sa.Text(), nullable=True),
        sa.Column("withdrawn_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("search_vector", postgresql.TSVECTOR(), server_default=sa.text("''::tsvector"), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.ForeignKeyConstraint(
            ["consent_id"],
            ["data_consents.id"],
            name=op.f("fk_learn_entries_consent_id_data_consents"),
            ondelete="SET NULL",
        ),
        sa.ForeignKeyConstraint(
            ["contributor_id"], ["users.id"], name=op.f("fk_learn_entries_contributor_id_users"), ondelete="SET NULL"
        ),
        sa.ForeignKeyConstraint(
            ["reviewer_id"], ["users.id"], name=op.f("fk_learn_entries_reviewer_id_users"), ondelete="SET NULL"
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_learn_entries")),
    )
    op.create_index(op.f("ix_learn_entries_contributor_id"), "learn_entries", ["contributor_id"], unique=False)
    op.create_index("ix_learn_entries_search", "learn_entries", ["search_vector"], unique=False, postgresql_using="gin")
    op.create_index("ix_learn_entries_status_category", "learn_entries", ["status", "category"], unique=False)
    op.create_table(
        "learn_entry_versions",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("entry_id", sa.Uuid(), nullable=False),
        sa.Column("version", sa.Integer(), nullable=False),
        sa.Column("title", sa.String(length=200), nullable=False),
        sa.Column("description", sa.Text(), nullable=False),
        sa.Column("technical_metadata", postgresql.JSONB(astext_type=sa.Text()), server_default="{}", nullable=False),
        sa.Column(
            "verification_status",
            sa.Enum(
                "unverified",
                "reviewed",
                "verified",
                name="learn_verification",
                native_enum=False,
                create_constraint=True,
                length=32,
            ),
            nullable=False,
        ),
        sa.Column("change", sa.String(length=32), nullable=False),
        sa.Column("changed_by_id", sa.Uuid(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.ForeignKeyConstraint(
            ["changed_by_id"],
            ["users.id"],
            name=op.f("fk_learn_entry_versions_changed_by_id_users"),
            ondelete="SET NULL",
        ),
        sa.ForeignKeyConstraint(
            ["entry_id"],
            ["learn_entries.id"],
            name=op.f("fk_learn_entry_versions_entry_id_learn_entries"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_learn_entry_versions")),
    )
    op.create_index(op.f("ix_learn_entry_versions_entry_id"), "learn_entry_versions", ["entry_id"], unique=False)
    op.create_table(
        "ai_output_knowledge",
        sa.Column("ai_output_id", sa.Uuid(), nullable=False),
        sa.Column("entry_id", sa.Uuid(), nullable=False),
        sa.Column("entry_version", sa.Integer(), nullable=False),
        sa.Column("rank", sa.Integer(), nullable=False),
        sa.Column("score", sa.Float(), nullable=False),
        sa.Column("cited", sa.Boolean(), server_default="false", nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.ForeignKeyConstraint(
            ["ai_output_id"],
            ["ai_outputs.id"],
            name=op.f("fk_ai_output_knowledge_ai_output_id_ai_outputs"),
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["entry_id"],
            ["learn_entries.id"],
            name=op.f("fk_ai_output_knowledge_entry_id_learn_entries"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("ai_output_id", "entry_id", name=op.f("pk_ai_output_knowledge")),
    )
    op.create_table(
        "recommendation_feedback",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("recommendation_id", sa.Uuid(), nullable=False),
        sa.Column("project_id", sa.Uuid(), nullable=False),
        sa.Column("design_id", sa.Uuid(), nullable=False),
        sa.Column("analysis_run_id", sa.Uuid(), nullable=True),
        sa.Column("user_id", sa.Uuid(), nullable=False),
        sa.Column("category", sa.String(length=32), nullable=False),
        sa.Column(
            "feedback_type",
            sa.Enum(
                "helpful",
                "unhelpful",
                "accepted",
                "rejected",
                "correction",
                "incorrect_assumption",
                "comment",
                name="feedback_type",
                native_enum=False,
                create_constraint=True,
                length=32,
            ),
            nullable=False,
        ),
        sa.Column("explanation", sa.Text(), nullable=True),
        sa.Column("model", sa.String(length=128), nullable=False),
        sa.Column("prompt_version", sa.String(length=32), nullable=False),
        sa.Column("engine_version", sa.String(length=32), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.ForeignKeyConstraint(
            ["analysis_run_id"],
            ["analysis_runs.id"],
            name=op.f("fk_recommendation_feedback_analysis_run_id_analysis_runs"),
            ondelete="SET NULL",
        ),
        sa.ForeignKeyConstraint(
            ["design_id"], ["designs.id"], name=op.f("fk_recommendation_feedback_design_id_designs"), ondelete="CASCADE"
        ),
        sa.ForeignKeyConstraint(
            ["project_id"],
            ["projects.id"],
            name=op.f("fk_recommendation_feedback_project_id_projects"),
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["recommendation_id"],
            ["recommendations.id"],
            name=op.f("fk_recommendation_feedback_recommendation_id_recommendations"),
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["user_id"], ["users.id"], name=op.f("fk_recommendation_feedback_user_id_users"), ondelete="CASCADE"
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_recommendation_feedback")),
    )
    op.create_index(
        op.f("ix_recommendation_feedback_project_id"), "recommendation_feedback", ["project_id"], unique=False
    )
    op.create_index(
        "ix_recommendation_feedback_rec_created",
        "recommendation_feedback",
        ["recommendation_id", "created_at"],
        unique=False,
    )
    op.create_index(op.f("ix_recommendation_feedback_user_id"), "recommendation_feedback", ["user_id"], unique=False)
    op.add_column("users", sa.Column("learn_reviewer", sa.Boolean(), server_default="false", nullable=False))


def downgrade() -> None:
    op.drop_column("users", "learn_reviewer")
    op.drop_index(op.f("ix_recommendation_feedback_user_id"), table_name="recommendation_feedback")
    op.drop_index("ix_recommendation_feedback_rec_created", table_name="recommendation_feedback")
    op.drop_index(op.f("ix_recommendation_feedback_project_id"), table_name="recommendation_feedback")
    op.drop_table("recommendation_feedback")
    op.drop_table("ai_output_knowledge")
    op.drop_index(op.f("ix_learn_entry_versions_entry_id"), table_name="learn_entry_versions")
    op.drop_table("learn_entry_versions")
    op.drop_index("ix_learn_entries_status_category", table_name="learn_entries")
    op.drop_index("ix_learn_entries_search", table_name="learn_entries", postgresql_using="gin")
    op.drop_index(op.f("ix_learn_entries_contributor_id"), table_name="learn_entries")
    op.drop_table("learn_entries")
