"""Analysis findings, their evidence and their review history (Stage 2).

Findings belong to one analysis run on one exact revision and are never updated by a
later run: re-running creates a new run with new rows. Only the review state (open /
reviewed / dismissed) changes, and every change is appended to ``finding_review_events``.
"""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any

from sqlalchemy import (
    Boolean,
    DateTime,
    Float,
    ForeignKey,
    Index,
    Integer,
    SmallInteger,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.dialects.postgresql import ARRAY, JSONB
from sqlalchemy.orm import Mapped, mapped_column

from via_api.models.base import Base, CreatedAt, Timestamps, UUIDPk, str_enum
from via_api.models.enums import FindingStatus
from via_pcb.analysis import Category, Severity, Source, Verification


class AnalysisFinding(UUIDPk, Timestamps, Base):
    __tablename__ = "analysis_findings"

    run_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("analysis_runs.id", ondelete="CASCADE"), index=True)
    # Denormalized for authorization and cross-revision comparison (single indexed lookups).
    project_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("projects.id", ondelete="CASCADE"), index=True)
    design_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("designs.id", ondelete="CASCADE"))
    revision_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("design_revisions.id", ondelete="CASCADE"), index=True)

    check_id: Mapped[str] = mapped_column(String(64))
    check_version: Mapped[str] = mapped_column(String(32))
    rule: Mapped[str] = mapped_column(String(64))
    category: Mapped[Category] = mapped_column(str_enum(Category, "finding_category"))
    severity: Mapped[Severity] = mapped_column(str_enum(Severity, "finding_severity"))
    #: 0 = critical ... 4 = info, for sorting by severity.
    severity_rank: Mapped[int] = mapped_column(SmallInteger)
    source: Mapped[Source] = mapped_column(str_enum(Source, "finding_source"))
    verification: Mapped[Verification] = mapped_column(str_enum(Verification, "finding_verification"))
    confidence: Mapped[float] = mapped_column(Float)

    title: Mapped[str] = mapped_column(String(300))
    description: Mapped[str] = mapped_column(Text)
    explanation: Mapped[str] = mapped_column(Text)
    suggested_resolution: Mapped[str | None] = mapped_column(Text)
    #: [{kind, id, label}] referencing objects of the analysed design by stable id.
    objects: Mapped[list[dict[str, Any]]] = mapped_column(JSONB, default=list, server_default="[]")
    components: Mapped[list[str]] = mapped_column(ARRAY(String(100)), default=list, server_default="{}")
    nets: Mapped[list[str]] = mapped_column(ARRAY(String(255)), default=list, server_default="{}")
    #: {bbox, points, layers} in board coordinates (mm), when the finding has a location.
    region: Mapped[dict[str, Any] | None] = mapped_column(JSONB)
    fingerprint: Mapped[str] = mapped_column(String(64))

    status: Mapped[FindingStatus] = mapped_column(
        str_enum(FindingStatus, "finding_status"), default=FindingStatus.OPEN, server_default=FindingStatus.OPEN.value
    )
    status_reason: Mapped[str | None] = mapped_column(Text)
    status_changed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    status_changed_by_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"))
    #: When the review state was carried over from the same issue in an earlier run.
    inherited_from_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("analysis_findings.id", ondelete="SET NULL"))


Index("ix_analysis_findings_run_severity", AnalysisFinding.run_id, AnalysisFinding.severity_rank)
Index("ix_analysis_findings_design_fingerprint", AnalysisFinding.design_id, AnalysisFinding.fingerprint)
Index("ix_analysis_findings_components", AnalysisFinding.components, postgresql_using="gin")
Index("ix_analysis_findings_nets", AnalysisFinding.nets, postgresql_using="gin")


class FindingEvidence(UUIDPk, CreatedAt, Base):
    __tablename__ = "finding_evidence"
    __table_args__ = (UniqueConstraint("finding_id", "ordinal"),)

    finding_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("analysis_findings.id", ondelete="CASCADE"))
    ordinal: Mapped[int] = mapped_column(Integer)
    kind: Mapped[str] = mapped_column(String(32))
    label: Mapped[str] = mapped_column(String(200))
    value: Mapped[str] = mapped_column(Text)
    numeric_value: Mapped[float | None] = mapped_column(Float)
    unit: Mapped[str | None] = mapped_column(String(32))
    expected: Mapped[str | None] = mapped_column(Text)


class FindingReviewEvent(UUIDPk, CreatedAt, Base):
    """Append-only history of review state changes."""

    __tablename__ = "finding_review_events"

    finding_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("analysis_findings.id", ondelete="CASCADE"), index=True)
    actor_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"))
    from_status: Mapped[FindingStatus] = mapped_column(str_enum(FindingStatus, "from_status"))
    to_status: Mapped[FindingStatus] = mapped_column(str_enum(FindingStatus, "to_status"))
    reason: Mapped[str | None] = mapped_column(Text)
    #: True when this event copied the state of the same issue from an earlier run.
    carried_over: Mapped[bool] = mapped_column(Boolean, default=False, server_default="false")
