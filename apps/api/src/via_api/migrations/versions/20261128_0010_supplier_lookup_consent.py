"""supplier lookup consent scope

Revision ID: 0010
Revises: 0009
Create Date: 2026-11-28 12:00:00.000000+00:00
"""

from collections.abc import Sequence

from alembic import op

revision: str = "0010"
down_revision: str | None = "0009"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.drop_constraint(op.f("ck_data_consents_consent_scope"), "data_consents", type_="check")
    op.create_check_constraint(
        "consent_scope",
        "data_consents",
        "scope IN ('via_learn_contribution', 'external_ai_processing', 'supplier_lookup')",
    )


def downgrade() -> None:
    op.execute("DELETE FROM data_consents WHERE scope = 'supplier_lookup'")
    op.drop_constraint(op.f("ck_data_consents_consent_scope"), "data_consents", type_="check")
    op.create_check_constraint(
        "consent_scope", "data_consents", "scope IN ('via_learn_contribution', 'external_ai_processing')"
    )
