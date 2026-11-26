"""Analysis runs, activity/audit log and consent records."""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any

from sqlalchemy import DateTime, ForeignKey, Index, Integer, String, Text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from via_api.models.base import Base, CreatedAt, Timestamps, UUIDPk, str_enum
from via_api.models.enums import AnalysisKind, AnalysisStatus, ConsentScope


class AnalysisRun(UUIDPk, Timestamps, Base):
    """A unit of processing on a revision. Stage 1 only records ``pcb_import`` runs.

    ``attempt``, ``job_id`` and ``heartbeat_at`` let the worker's reaper detect work
    whose worker died (stale heartbeat) or whose queued job was lost, and retry it a
    bounded number of times (see ``via_api.jobs``).
    """

    __tablename__ = "analysis_runs"

    project_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("projects.id", ondelete="CASCADE"))
    revision_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("design_revisions.id", ondelete="CASCADE"), index=True
    )
    kind: Mapped[AnalysisKind] = mapped_column(str_enum(AnalysisKind, "analysis_kind"))
    status: Mapped[AnalysisStatus] = mapped_column(
        str_enum(AnalysisStatus, "analysis_status"),
        default=AnalysisStatus.QUEUED,
        server_default=AnalysisStatus.QUEUED.value,
    )
    engine_version: Mapped[str | None] = mapped_column(String(32))
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    error_code: Mapped[str | None] = mapped_column(String(64))
    error_message: Mapped[str | None] = mapped_column(Text)
    result_summary: Mapped[dict[str, Any]] = mapped_column(JSONB, default=dict, server_default="{}")
    triggered_by_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"))
    #: 1 for the first try; incremented each time the reaper re-queues the work.
    attempt: Mapped[int] = mapped_column(Integer, default=0, server_default="0")
    #: Queue job id of the current attempt; callbacks from superseded attempts are ignored.
    job_id: Mapped[str | None] = mapped_column(String(128))
    #: Last sign of life from the process doing the work (updated every few seconds).
    heartbeat_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    # Provenance of analysis runs (kind = pcb_analysis): exactly what produced the findings.
    #: Options the run was started with (e.g. selected checks; manufacturing profile from M3).
    config: Mapped[dict[str, Any]] = mapped_column(JSONB, default=dict, server_default="{}")
    #: Per-check outcome: [{check_id, version, status, finding_count, duration_ms, message}].
    checks: Mapped[list[dict[str, Any]]] = mapped_column(JSONB, default=list, server_default="[]")
    analysis_version: Mapped[str | None] = mapped_column(String(32))
    #: Parser and schema version of the design that was analysed.
    design_parser_version: Mapped[str | None] = mapped_column(String(32))
    design_schema_version: Mapped[str | None] = mapped_column(String(32))


class ActivityLog(UUIDPk, CreatedAt, Base):
    """User-visible activity and security audit trail (append-only).

    ``project_id``/``organization_id`` are SET NULL on delete so audit entries
    outlive the objects they describe; ``target_id`` deliberately has no FK.
    """

    __tablename__ = "activity_logs"

    actor_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"))
    organization_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("organizations.id", ondelete="SET NULL"))
    project_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("projects.id", ondelete="SET NULL"))
    action: Mapped[str] = mapped_column(String(64), index=True)
    target_type: Mapped[str | None] = mapped_column(String(32))
    target_id: Mapped[uuid.UUID | None] = mapped_column()
    ip_address: Mapped[str | None] = mapped_column(String(45))
    user_agent: Mapped[str | None] = mapped_column(String(512))
    details: Mapped[dict[str, Any]] = mapped_column(JSONB, default=dict, server_default="{}")


class DataConsent(UUIDPk, CreatedAt, Base):
    """Explicit, scoped, revocable consent. No row = no consent.

    Nothing in Stage 1 grants or uses consent. Future VIA Learn contributions
    must reference an active consent row, and will store only derived,
    de-identified artefacts in separate tables with no foreign key back to
    private project data (see docs/DATABASE.md).
    """

    __tablename__ = "data_consents"

    user_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"))
    project_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("projects.id", ondelete="CASCADE"))
    scope: Mapped[ConsentScope] = mapped_column(str_enum(ConsentScope, "consent_scope"))
    policy_version: Mapped[str] = mapped_column(String(32))
    granted_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    revoked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


Index("ix_activity_logs_project_created", ActivityLog.project_id, ActivityLog.created_at.desc())
Index("ix_activity_logs_actor_created", ActivityLog.actor_id, ActivityLog.created_at.desc())
Index("ix_analysis_runs_project_created", AnalysisRun.project_id, AnalysisRun.created_at.desc())
Index("ix_analysis_runs_kind_status", AnalysisRun.kind, AnalysisRun.status)
Index("ix_data_consents_user_scope", DataConsent.user_id, DataConsent.scope)
