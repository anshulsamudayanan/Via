"""analysis findings

Revision ID: 0004
Revises: 0003
Create Date: 2026-11-26 06:07:55.665810+00:00
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0004"
down_revision: str | None = "0003"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # VARCHAR + CHECK enum: autogenerate doesn't see the new value (hand-written).
    op.drop_constraint(op.f("ck_analysis_runs_analysis_kind"), "analysis_runs", type_="check")
    op.create_check_constraint("analysis_kind", "analysis_runs", "kind IN ('pcb_import', 'pcb_analysis')")
    op.create_table(
        "analysis_findings",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("run_id", sa.Uuid(), nullable=False),
        sa.Column("project_id", sa.Uuid(), nullable=False),
        sa.Column("design_id", sa.Uuid(), nullable=False),
        sa.Column("revision_id", sa.Uuid(), nullable=False),
        sa.Column("check_id", sa.String(length=64), nullable=False),
        sa.Column("check_version", sa.String(length=32), nullable=False),
        sa.Column("rule", sa.String(length=64), nullable=False),
        sa.Column(
            "category",
            sa.Enum(
                "geometry",
                "board_outline",
                "design_rules",
                "connectivity",
                "routing",
                "placement",
                "manufacturing",
                "thermal",
                "power",
                "signal_integrity",
                "import",
                name="finding_category",
                native_enum=False,
                create_constraint=True,
                length=32,
            ),
            nullable=False,
        ),
        sa.Column(
            "severity",
            sa.Enum(
                "critical",
                "high",
                "medium",
                "low",
                "info",
                name="finding_severity",
                native_enum=False,
                create_constraint=True,
                length=32,
            ),
            nullable=False,
        ),
        sa.Column("severity_rank", sa.SmallInteger(), nullable=False),
        sa.Column(
            "source",
            sa.Enum(
                "via_deterministic",
                "kicad_drc",
                "external_simulation",
                "ai_suggestion",
                name="finding_source",
                native_enum=False,
                create_constraint=True,
                length=32,
            ),
            nullable=False,
        ),
        sa.Column(
            "verification",
            sa.Enum(
                "verified",
                "heuristic",
                "unverified",
                name="finding_verification",
                native_enum=False,
                create_constraint=True,
                length=32,
            ),
            nullable=False,
        ),
        sa.Column("confidence", sa.Float(), nullable=False),
        sa.Column("title", sa.String(length=300), nullable=False),
        sa.Column("description", sa.Text(), nullable=False),
        sa.Column("explanation", sa.Text(), nullable=False),
        sa.Column("suggested_resolution", sa.Text(), nullable=True),
        sa.Column("objects", postgresql.JSONB(astext_type=sa.Text()), server_default="[]", nullable=False),
        sa.Column("components", postgresql.ARRAY(sa.String(length=100)), server_default="{}", nullable=False),
        sa.Column("nets", postgresql.ARRAY(sa.String(length=255)), server_default="{}", nullable=False),
        sa.Column("region", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("fingerprint", sa.String(length=64), nullable=False),
        sa.Column(
            "status",
            sa.Enum(
                "open",
                "reviewed",
                "dismissed",
                name="finding_status",
                native_enum=False,
                create_constraint=True,
                length=32,
            ),
            server_default="open",
            nullable=False,
        ),
        sa.Column("status_reason", sa.Text(), nullable=True),
        sa.Column("status_changed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("status_changed_by_id", sa.Uuid(), nullable=True),
        sa.Column("inherited_from_id", sa.Uuid(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.ForeignKeyConstraint(
            ["design_id"], ["designs.id"], name=op.f("fk_analysis_findings_design_id_designs"), ondelete="CASCADE"
        ),
        sa.ForeignKeyConstraint(
            ["inherited_from_id"],
            ["analysis_findings.id"],
            name=op.f("fk_analysis_findings_inherited_from_id_analysis_findings"),
            ondelete="SET NULL",
        ),
        sa.ForeignKeyConstraint(
            ["project_id"], ["projects.id"], name=op.f("fk_analysis_findings_project_id_projects"), ondelete="CASCADE"
        ),
        sa.ForeignKeyConstraint(
            ["revision_id"],
            ["design_revisions.id"],
            name=op.f("fk_analysis_findings_revision_id_design_revisions"),
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["run_id"], ["analysis_runs.id"], name=op.f("fk_analysis_findings_run_id_analysis_runs"), ondelete="CASCADE"
        ),
        sa.ForeignKeyConstraint(
            ["status_changed_by_id"],
            ["users.id"],
            name=op.f("fk_analysis_findings_status_changed_by_id_users"),
            ondelete="SET NULL",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_analysis_findings")),
    )
    op.create_index(
        "ix_analysis_findings_components", "analysis_findings", ["components"], unique=False, postgresql_using="gin"
    )
    op.create_index(
        "ix_analysis_findings_design_fingerprint", "analysis_findings", ["design_id", "fingerprint"], unique=False
    )
    op.create_index("ix_analysis_findings_nets", "analysis_findings", ["nets"], unique=False, postgresql_using="gin")
    op.create_index(op.f("ix_analysis_findings_project_id"), "analysis_findings", ["project_id"], unique=False)
    op.create_index(op.f("ix_analysis_findings_revision_id"), "analysis_findings", ["revision_id"], unique=False)
    op.create_index(op.f("ix_analysis_findings_run_id"), "analysis_findings", ["run_id"], unique=False)
    op.create_index("ix_analysis_findings_run_severity", "analysis_findings", ["run_id", "severity_rank"], unique=False)
    op.create_table(
        "finding_evidence",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("finding_id", sa.Uuid(), nullable=False),
        sa.Column("ordinal", sa.Integer(), nullable=False),
        sa.Column("kind", sa.String(length=32), nullable=False),
        sa.Column("label", sa.String(length=200), nullable=False),
        sa.Column("value", sa.Text(), nullable=False),
        sa.Column("numeric_value", sa.Float(), nullable=True),
        sa.Column("unit", sa.String(length=32), nullable=True),
        sa.Column("expected", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.ForeignKeyConstraint(
            ["finding_id"],
            ["analysis_findings.id"],
            name=op.f("fk_finding_evidence_finding_id_analysis_findings"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_finding_evidence")),
        sa.UniqueConstraint("finding_id", "ordinal", name=op.f("uq_finding_evidence_finding_id_ordinal")),
    )
    op.create_table(
        "finding_review_events",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("finding_id", sa.Uuid(), nullable=False),
        sa.Column("actor_id", sa.Uuid(), nullable=True),
        sa.Column(
            "from_status",
            sa.Enum(
                "open",
                "reviewed",
                "dismissed",
                name="from_status",
                native_enum=False,
                create_constraint=True,
                length=32,
            ),
            nullable=False,
        ),
        sa.Column(
            "to_status",
            sa.Enum(
                "open", "reviewed", "dismissed", name="to_status", native_enum=False, create_constraint=True, length=32
            ),
            nullable=False,
        ),
        sa.Column("reason", sa.Text(), nullable=True),
        sa.Column("carried_over", sa.Boolean(), server_default="false", nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.ForeignKeyConstraint(
            ["actor_id"], ["users.id"], name=op.f("fk_finding_review_events_actor_id_users"), ondelete="SET NULL"
        ),
        sa.ForeignKeyConstraint(
            ["finding_id"],
            ["analysis_findings.id"],
            name=op.f("fk_finding_review_events_finding_id_analysis_findings"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_finding_review_events")),
    )
    op.create_index(op.f("ix_finding_review_events_finding_id"), "finding_review_events", ["finding_id"], unique=False)
    op.add_column(
        "analysis_runs",
        sa.Column("config", postgresql.JSONB(astext_type=sa.Text()), server_default="{}", nullable=False),
    )
    op.add_column(
        "analysis_runs",
        sa.Column("checks", postgresql.JSONB(astext_type=sa.Text()), server_default="[]", nullable=False),
    )
    op.add_column("analysis_runs", sa.Column("analysis_version", sa.String(length=32), nullable=True))
    op.add_column("analysis_runs", sa.Column("design_parser_version", sa.String(length=32), nullable=True))
    op.add_column("analysis_runs", sa.Column("design_schema_version", sa.String(length=32), nullable=True))


def downgrade() -> None:
    op.execute("DELETE FROM analysis_runs WHERE kind = 'pcb_analysis'")
    op.drop_constraint(op.f("ck_analysis_runs_analysis_kind"), "analysis_runs", type_="check")
    op.create_check_constraint("analysis_kind", "analysis_runs", "kind IN ('pcb_import')")
    op.drop_column("analysis_runs", "design_schema_version")
    op.drop_column("analysis_runs", "design_parser_version")
    op.drop_column("analysis_runs", "analysis_version")
    op.drop_column("analysis_runs", "checks")
    op.drop_column("analysis_runs", "config")
    op.drop_index(op.f("ix_finding_review_events_finding_id"), table_name="finding_review_events")
    op.drop_table("finding_review_events")
    op.drop_table("finding_evidence")
    op.drop_index("ix_analysis_findings_run_severity", table_name="analysis_findings")
    op.drop_index(op.f("ix_analysis_findings_run_id"), table_name="analysis_findings")
    op.drop_index(op.f("ix_analysis_findings_revision_id"), table_name="analysis_findings")
    op.drop_index(op.f("ix_analysis_findings_project_id"), table_name="analysis_findings")
    op.drop_index("ix_analysis_findings_nets", table_name="analysis_findings", postgresql_using="gin")
    op.drop_index("ix_analysis_findings_design_fingerprint", table_name="analysis_findings")
    op.drop_index("ix_analysis_findings_components", table_name="analysis_findings", postgresql_using="gin")
    op.drop_table("analysis_findings")
