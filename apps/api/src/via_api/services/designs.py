"""Designs, revisions and PCB uploads.

Uploads are validated here (size, type, duplicates) and stored in object
storage; parsing happens later in the worker. Every function that takes a
design id resolves it through :func:`get_design`, which applies the project's
authorization rules (a design in a project you can't see is "not found").
"""

from __future__ import annotations

import hashlib
import logging
import os
import re
import uuid
from typing import Any, BinaryIO

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from via_api.errors import APIError, not_found
from via_api.models import Design, DesignFile, DesignRevision, Project, UploadRecord, User
from via_api.models.base import utcnow
from via_api.models.enums import DesignFileKind, ProjectRole, RevisionStatus, UploadOutcome
from via_api.schemas.pcb import DesignDetail, DesignOut, FileOut, RevisionOut, WarningOut
from via_api.schemas.projects import UserRef
from via_api.services import access, activity
from via_api.services.activity import ClientInfo
from via_api.services.auth import AuthContext
from via_api.storage import StorageBackend, StorageError, revision_object_key
from via_pcb import (
    ARCHIVE_EXTENSIONS,
    AdapterNotFoundError,
    ArchiveLimits,
    ProjectArchiveError,
    detect_adapter,
    get_registry,
    inspect_project,
    is_project_archive,
)
from via_pcb.adapters import KiCadAdapter

logger = logging.getLogger("via_api.designs")

DESIGN_UPLOADED = "design.uploaded"
DESIGN_UPLOAD_REJECTED = "design.upload_rejected"
DESIGN_UPDATED = "design.updated"
DESIGN_DELETED = "design.deleted"

SNIFF_BYTES = 4096
CHUNK = 1024 * 1024


# ----------------------------------------------------------------- lookups


def get_design(
    db: Session,
    user_id: uuid.UUID,
    design_id: uuid.UUID,
    minimum: ProjectRole = ProjectRole.VIEWER,
    *,
    action: str = "do that",
) -> tuple[Design, Project, ProjectRole]:
    design = db.get(Design, design_id)
    if design is None:
        raise not_found("Design")
    try:
        project, role = access.get_project(db, user_id, design.project_id, minimum, action=action)
    except APIError as exc:
        if exc.status_code == 404:
            raise not_found("Design") from exc
        raise
    return design, project, role


def get_revision(db: Session, user_id: uuid.UUID, revision_id: uuid.UUID) -> tuple[DesignRevision, Design]:
    revision = db.get(DesignRevision, revision_id)
    if revision is None:
        raise not_found("Revision")
    try:
        design, _, _ = get_design(db, user_id, revision.design_id)
    except APIError as exc:
        if exc.status_code == 404:
            raise not_found("Revision") from exc
        raise
    return revision, design


def resolve_parsed_revision(db: Session, design: Design, revision_id: uuid.UUID | None) -> DesignRevision:
    """The revision PCB endpoints read: the requested one, or the design's current parsed revision."""
    if revision_id is not None:
        revision = db.get(DesignRevision, revision_id)
        if revision is None or revision.design_id != design.id:
            raise not_found("Revision")
    else:
        revision = db.get(DesignRevision, design.current_revision_id) if design.current_revision_id else None
        if revision is None:
            raise APIError(409, "not_parsed", "This design has no successfully parsed revision yet.")
    if revision.status != RevisionStatus.READY:
        raise APIError(
            409, "not_parsed", f"Revision {revision.revision_number} is {revision.status.value}, not parsed."
        )
    return revision


# ----------------------------------------------------------------- serialization


def _user_ref(db: Session, user_id: uuid.UUID | None) -> UserRef | None:
    user = db.get(User, user_id) if user_id else None
    return UserRef.model_validate(user) if user else None


def revision_out(db: Session, revision: DesignRevision) -> RevisionOut:
    source = db.scalar(
        select(DesignFile).where(DesignFile.revision_id == revision.id, DesignFile.kind == DesignFileKind.SOURCE)
    )
    return RevisionOut(
        id=revision.id,
        design_id=revision.design_id,
        project_id=revision.project_id,
        revision_number=revision.revision_number,
        status=revision.status,
        source_format=revision.source_format,
        source_sha256=revision.source_sha256,
        parser_version=revision.parser_version,
        schema_version=revision.schema_version,
        imported_at=revision.imported_at,
        error_code=revision.error_code,
        error_message=revision.error_message,
        warnings=[WarningOut(**w) for w in revision.warnings],
        object_counts=revision.object_counts,
        created_by=_user_ref(db, revision.created_by_id),
        created_at=revision.created_at,
        source_file=FileOut.model_validate(source) if source else None,
    )


def _design_fields(db: Session, design: Design) -> tuple[dict[str, Any], list[RevisionOut]]:
    revisions = list(
        db.scalars(
            select(DesignRevision)
            .where(DesignRevision.design_id == design.id)
            .order_by(DesignRevision.revision_number.desc())
        )
    )
    outs = {r.id: revision_out(db, r) for r in revisions}
    base = {
        "id": design.id,
        "project_id": design.project_id,
        "name": design.name,
        "description": design.description,
        "created_by": _user_ref(db, design.created_by_id),
        "created_at": design.created_at,
        "updated_at": design.updated_at,
        "revision_count": len(revisions),
        "current_revision": outs.get(design.current_revision_id) if design.current_revision_id else None,
        "latest_revision": outs[revisions[0].id] if revisions else None,
    }
    return base, list(outs.values())


def design_out(db: Session, design: Design) -> DesignOut:
    base, _ = _design_fields(db, design)
    return DesignOut.model_validate(base)


def design_detail(db: Session, design: Design) -> DesignDetail:
    base, revisions = _design_fields(db, design)
    return DesignDetail.model_validate({**base, "revisions": revisions})


def list_designs(db: Session, project_id: uuid.UUID) -> list[DesignOut]:
    designs = db.scalars(select(Design).where(Design.project_id == project_id).order_by(Design.updated_at.desc()))
    return [design_out(db, d) for d in designs]


# ----------------------------------------------------------------- upload


def next_revision_number(db: Session, design_id: uuid.UUID) -> int:
    """The next revision number, with the design row locked so concurrent uploads/exports can't collide."""
    db.execute(select(Design.id).where(Design.id == design_id).with_for_update())
    latest = db.scalar(select(func.max(DesignRevision.revision_number)).where(DesignRevision.design_id == design_id))
    return (latest or 0) + 1


def clean_filename(filename: str | None) -> str:
    base = os.path.basename((filename or "").replace("\\", "/"))
    base = re.sub(r"[\x00-\x1f\x7f]", "", base).strip()
    return base[:255] or "upload"


def _reject(
    db: Session,
    ctx: AuthContext,
    project: Project,
    client: ClientInfo,
    *,
    filename: str,
    size: int,
    sha256: str | None,
    outcome: UploadOutcome,
    reason: str,
    error: APIError,
) -> APIError:
    """Record a rejected upload (audit + duplicate stats), commit, and return the error to raise."""
    db.rollback()
    db.add(
        UploadRecord(
            project_id=project.id,
            user_id=ctx.user.id,
            original_filename=filename,
            size_bytes=size,
            sha256=sha256,
            outcome=outcome,
            rejection_reason=reason,
            ip_address=client.ip_address,
        )
    )
    activity.record(
        db,
        DESIGN_UPLOAD_REJECTED,
        actor_id=ctx.user.id,
        client=client,
        project_id=project.id,
        details={"filename": filename, "reason": reason},
    )
    db.commit()
    return error


def import_upload(
    db: Session,
    storage: StorageBackend,
    ctx: AuthContext,
    project: Project,
    *,
    stream: BinaryIO,
    filename: str | None,
    content_type: str | None,
    design_id: uuid.UUID | None,
    name: str | None,
    max_bytes: int,
    client: ClientInfo,
) -> tuple[Design, DesignRevision]:
    access.ensure_active(project)
    fname = clean_filename(filename)

    # Hash and measure while reading; never trust Content-Length alone.
    digest = hashlib.sha256()
    size = 0
    head = b""
    stream.seek(0)
    while chunk := stream.read(CHUNK):
        size += len(chunk)
        if size > max_bytes:
            raise _reject(
                db,
                ctx,
                project,
                client,
                filename=fname,
                size=size,
                sha256=None,
                outcome=UploadOutcome.REJECTED,
                reason="too_large",
                error=APIError(
                    413, "payload_too_large", f"The file is larger than the {max_bytes // (1024 * 1024)} MB limit."
                ),
            )
        if len(head) < SNIFF_BYTES:
            head += chunk[: SNIFF_BYTES - len(head)]
        digest.update(chunk)
    sha256 = digest.hexdigest()

    if size == 0:
        raise _reject(
            db,
            ctx,
            project,
            client,
            filename=fname,
            size=0,
            sha256=None,
            outcome=UploadOutcome.REJECTED,
            reason="empty",
            error=APIError(422, "empty_file", "The file is empty."),
        )
    source_format: str
    if is_project_archive(fname, head):
        # A KiCad project archive: validate it and choose its board from the central directory
        # (nothing is decompressed here); the sandboxed parser reads it again in full.
        try:
            stream.seek(0)
            inspect_project(stream, ArchiveLimits(max_board_bytes=max_bytes))
        except ProjectArchiveError as exc:
            raise _reject(
                db,
                ctx,
                project,
                client,
                filename=fname,
                size=size,
                sha256=sha256,
                outcome=UploadOutcome.REJECTED,
                reason="invalid_archive",
                error=APIError(422, "invalid_project_archive", str(exc)),
            ) from None
        source_format = KiCadAdapter.format_id
    else:
        try:
            source_format = detect_adapter(fname, head).format_id
        except AdapterNotFoundError:
            source_format = ""
    if not source_format:
        exts = ", ".join(sorted(get_registry().extensions | set(ARCHIVE_EXTENSIONS)))
        raise _reject(
            db,
            ctx,
            project,
            client,
            filename=fname,
            size=size,
            sha256=sha256,
            outcome=UploadOutcome.REJECTED,
            reason="unsupported_type",
            error=APIError(
                415, "unsupported_file_type", f"This isn't a supported PCB file. Supported formats: {exts}."
            ),
        )

    existing = db.execute(
        select(DesignRevision, Design)
        .join(Design, Design.id == DesignRevision.design_id)
        .where(
            DesignRevision.project_id == project.id,
            DesignRevision.source_sha256 == sha256,
            DesignRevision.status != RevisionStatus.FAILED,
        )
        .limit(1)
    ).first()
    if existing is not None:
        rev, des = existing
        raise _reject(
            db,
            ctx,
            project,
            client,
            filename=fname,
            size=size,
            sha256=sha256,
            outcome=UploadOutcome.DUPLICATE,
            reason="duplicate",
            error=APIError(
                409,
                "duplicate_file",
                f'This exact file is already in the project as "{des.name}" revision {rev.revision_number}.',
                {"design_id": str(des.id), "revision_id": str(rev.id), "design_name": des.name},
            ),
        )

    if design_id is not None:
        design = db.get(Design, design_id)
        if design is None or design.project_id != project.id:
            raise not_found("Design")
        design.updated_at = utcnow()
    else:
        design_name = (name or "").strip() or os.path.splitext(fname)[0] or "Untitled design"
        design = Design(project_id=project.id, name=design_name[:200], created_by_id=ctx.user.id)
        db.add(design)
        db.flush()

    number = next_revision_number(db, design.id)
    revision = DesignRevision(
        design_id=design.id,
        project_id=project.id,
        revision_number=number,
        status=RevisionStatus.PENDING,
        source_format=source_format,
        source_sha256=sha256,
        created_by_id=ctx.user.id,
    )
    db.add(revision)
    db.flush()

    key = revision_object_key(project.id, revision.id, "source")
    stream.seek(0)
    try:
        storage.put(key, stream, content_type="application/octet-stream", size=size)
    except StorageError as exc:
        db.rollback()
        logger.error("Storing upload failed: %s", exc)
        raise APIError(503, "storage_unavailable", "File storage is unavailable. Please try again shortly.") from exc

    db.add(
        DesignFile(
            revision_id=revision.id,
            project_id=project.id,
            kind=DesignFileKind.SOURCE,
            storage_key=key,
            original_filename=fname,
            content_type=(content_type or "application/octet-stream")[:127],
            size_bytes=size,
            sha256=sha256,
        )
    )
    db.add(
        UploadRecord(
            project_id=project.id,
            user_id=ctx.user.id,
            original_filename=fname,
            size_bytes=size,
            sha256=sha256,
            content_type=(content_type or None) and content_type[:127],
            outcome=UploadOutcome.ACCEPTED,
            revision_id=revision.id,
            ip_address=client.ip_address,
        )
    )
    activity.record(
        db,
        DESIGN_UPLOADED,
        actor_id=ctx.user.id,
        client=client,
        project_id=project.id,
        target_type="design",
        target_id=design.id,
        details={"design": design.name, "revision": number, "filename": fname, "size_bytes": size},
    )
    return design, revision


# ----------------------------------------------------------------- deletion


def storage_keys(db: Session, *, design_id: uuid.UUID | None = None, project_id: uuid.UUID | None = None) -> list[str]:
    stmt = select(DesignFile.storage_key)
    if design_id is not None:
        stmt = stmt.join(DesignRevision, DesignRevision.id == DesignFile.revision_id).where(
            DesignRevision.design_id == design_id
        )
    if project_id is not None:
        stmt = stmt.where(DesignFile.project_id == project_id)
    return list(db.scalars(stmt))


def delete_objects(storage: StorageBackend, keys: list[str]) -> None:
    """Best-effort removal after the database rows are gone (failures are logged, not raised)."""
    for key in keys:
        try:
            storage.delete(key)
        except StorageError as exc:
            logger.error("Could not delete stored object %s: %s", key, exc)


def delete_design(db: Session, ctx: AuthContext, design: Design, client: ClientInfo) -> list[str]:
    keys = storage_keys(db, design_id=design.id)
    activity.record(
        db,
        DESIGN_DELETED,
        actor_id=ctx.user.id,
        client=client,
        project_id=design.project_id,
        target_type="design",
        target_id=design.id,
        details={"design": design.name},
    )
    design.current_revision_id = None
    db.flush()
    db.delete(design)
    return keys
