"""Designs, revisions, stored files and upload attempts.

File *contents* never live in PostgreSQL: ``DesignFile`` holds only metadata and
an object-storage key.
"""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any

from sqlalchemy import BigInteger, DateTime, ForeignKey, Index, Integer, String, Text, UniqueConstraint
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship

from via_api.models.base import Base, CreatedAt, Timestamps, UUIDPk, str_enum
from via_api.models.enums import DesignFileKind, RevisionStatus, UploadOutcome


class Design(UUIDPk, Timestamps, Base):
    __tablename__ = "designs"

    project_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("projects.id", ondelete="CASCADE"), index=True)
    name: Mapped[str] = mapped_column(String(200))
    description: Mapped[str] = mapped_column(Text, default="", server_default="")
    created_by_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"))
    #: Latest successfully parsed revision; set by the import pipeline.
    current_revision_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("design_revisions.id", ondelete="SET NULL", use_alter=True)
    )

    revisions: Mapped[list[DesignRevision]] = relationship(
        back_populates="design",
        cascade="all, delete-orphan",
        foreign_keys="DesignRevision.design_id",
        order_by="DesignRevision.revision_number",
    )


class DesignRevision(UUIDPk, Timestamps, Base):
    """One uploaded version of a design and the outcome of parsing it."""

    __tablename__ = "design_revisions"
    __table_args__ = (UniqueConstraint("design_id", "revision_number"),)

    design_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("designs.id", ondelete="CASCADE"))
    #: Denormalized for authorization checks and per-project queries.
    project_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("projects.id", ondelete="CASCADE"), index=True)
    revision_number: Mapped[int] = mapped_column(Integer)
    status: Mapped[RevisionStatus] = mapped_column(
        str_enum(RevisionStatus, "revision_status"),
        default=RevisionStatus.PENDING,
        server_default=RevisionStatus.PENDING.value,
        index=True,
    )
    source_format: Mapped[str] = mapped_column(String(32))
    source_sha256: Mapped[str] = mapped_column(String(64))
    parser_version: Mapped[str | None] = mapped_column(String(32))
    schema_version: Mapped[str | None] = mapped_column(String(32))
    imported_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    error_code: Mapped[str | None] = mapped_column(String(64))
    #: Safe, user-facing message only (no stack traces).
    error_message: Mapped[str | None] = mapped_column(Text)
    warnings: Mapped[list[dict[str, Any]]] = mapped_column(JSONB, default=list, server_default="[]")
    object_counts: Mapped[dict[str, Any]] = mapped_column(JSONB, default=dict, server_default="{}")
    created_by_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"))

    design: Mapped[Design] = relationship(back_populates="revisions", foreign_keys=[design_id])
    files: Mapped[list[DesignFile]] = relationship(back_populates="revision", cascade="all, delete-orphan")


class DesignFile(UUIDPk, CreatedAt, Base):
    """Metadata for a file held in object storage (source upload or normalized JSON)."""

    __tablename__ = "design_files"

    revision_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("design_revisions.id", ondelete="CASCADE"), index=True)
    project_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("projects.id", ondelete="CASCADE"))
    kind: Mapped[DesignFileKind] = mapped_column(str_enum(DesignFileKind, "design_file_kind"))
    #: Server-generated key; never derived from user input.
    storage_key: Mapped[str] = mapped_column(String(512), unique=True)
    original_filename: Mapped[str | None] = mapped_column(String(255))
    content_type: Mapped[str] = mapped_column(String(127))
    size_bytes: Mapped[int] = mapped_column(BigInteger)
    sha256: Mapped[str] = mapped_column(String(64))

    revision: Mapped[DesignRevision] = relationship(back_populates="files")


class UploadRecord(UUIDPk, CreatedAt, Base):
    """Every upload attempt, accepted or not: audit trail and duplicate detection."""

    __tablename__ = "upload_records"

    project_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("projects.id", ondelete="CASCADE"))
    user_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"), index=True)
    original_filename: Mapped[str] = mapped_column(String(255))
    size_bytes: Mapped[int] = mapped_column(BigInteger)
    sha256: Mapped[str | None] = mapped_column(String(64))
    content_type: Mapped[str | None] = mapped_column(String(127))
    outcome: Mapped[UploadOutcome] = mapped_column(str_enum(UploadOutcome, "upload_outcome"))
    rejection_reason: Mapped[str | None] = mapped_column(String(255))
    revision_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("design_revisions.id", ondelete="SET NULL"))
    ip_address: Mapped[str | None] = mapped_column(String(45))


Index("ix_design_files_project_sha256", DesignFile.project_id, DesignFile.sha256)
Index("ix_design_revisions_project_sha256", DesignRevision.project_id, DesignRevision.source_sha256)
Index("ix_upload_records_project_created", UploadRecord.project_id, UploadRecord.created_at)
