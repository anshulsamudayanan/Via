"""/api/v1/pcb: upload (import) and read parsed boards."""

from __future__ import annotations

import uuid
from typing import Annotated

from fastapi import APIRouter, File, Form, Query, Response, UploadFile, status
from sqlalchemy import Integer, cast, func, select

from via_api.deps import DB, AppSettings, Client, CurrentAuth, Limiter, Queue, Storage
from via_api.errors import APIError, error_responses
from via_api.models import DesignFile, PCBComponent, PCBGeometry, PCBLayer, PCBNet
from via_api.models.enums import DesignFileKind, ProjectRole
from via_api.parsing.importer import mark_failed
from via_api.ratelimit import Limit
from via_api.schemas.common import DEFAULT_LIMIT, MAX_LIMIT, Page
from via_api.schemas.pcb import (
    BoardSummary,
    ComponentOut,
    DesignRef,
    FormatInfo,
    GeometryOut,
    ImportResponse,
    LayerOut,
    NetOut,
    UploadLimits,
    WarningOut,
)
from via_api.services import access
from via_api.services import designs as svc
from via_api.storage import ObjectNotFoundError, StorageError

router = APIRouter(prefix="/pcb", tags=["pcb"])

UPLOADS_PER_USER = Limit("upload-user", 60, 3600)
IMPORT_PATH = "/api/v1/pcb/import"


def _escape_like(term: str) -> str:
    return term.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")


@router.get("/limits", response_model=UploadLimits, responses=error_responses(401))
def upload_limits(settings: AppSettings, ctx: CurrentAuth) -> UploadLimits:
    """Accepted formats and the maximum upload size (for client-side validation)."""
    from via_pcb import get_registry

    formats = [
        FormatInfo(id=a.format_id, name=a.display_name, extensions=list(a.extensions)) for a in get_registry().all()
    ]
    return UploadLimits(max_upload_bytes=settings.max_upload_bytes, formats=formats)


@router.post(
    "/import",
    response_model=ImportResponse,
    status_code=status.HTTP_202_ACCEPTED,
    responses=error_responses(401, 403, 404, 409, 411, 413, 415, 422, 429, 503),
)
def import_pcb(
    db: DB,
    settings: AppSettings,
    client: Client,
    ctx: CurrentAuth,
    limiter: Limiter,
    storage: Storage,
    queue: Queue,
    project_id: Annotated[uuid.UUID, Form()],
    file: Annotated[UploadFile, File(description="KiCad .kicad_pcb file")],
    design_id: Annotated[uuid.UUID | None, Form(description="Add a new revision to this design")] = None,
    name: Annotated[str | None, Form(max_length=200, description="Name for a new design")] = None,
) -> ImportResponse:
    """Upload a PCB file. It's validated and stored now, and parsed in the background.

    Poll `GET /api/v1/revisions/{id}` until `status` is `ready` or `failed`.
    """
    project, _ = access.get_project(db, ctx.user.id, project_id, ProjectRole.EDITOR, action="upload designs")
    limiter.hit(UPLOADS_PER_USER, str(ctx.user.id))
    design, revision = svc.import_upload(
        db,
        storage,
        ctx,
        project,
        stream=file.file,
        filename=file.filename,
        content_type=file.content_type,
        design_id=design_id,
        name=name,
        max_bytes=settings.max_upload_bytes,
        client=client,
    )
    db.commit()
    try:
        queue.enqueue_import(revision.id)
    except Exception as exc:  # Redis down: don't leave the revision pending forever
        mark_failed(db, revision, "queue_unavailable", "Processing couldn't be started. Please upload the file again.")
        db.commit()
        raise APIError(503, "queue_unavailable", "Processing couldn't be started. Please try again shortly.") from exc
    db.refresh(revision)
    return ImportResponse(design=svc.design_out(db, design), revision=svc.revision_out(db, revision))


@router.get("/{design_id}", response_model=BoardSummary, responses=error_responses(401, 404, 409))
def board_summary(design_id: uuid.UUID, db: DB, ctx: CurrentAuth, revision_id: uuid.UUID | None = None) -> BoardSummary:
    """Board information for the design's current parsed revision (or `revision_id`)."""
    design, _, _ = svc.get_design(db, ctx.user.id, design_id)
    revision = svc.resolve_parsed_revision(db, design, revision_id)
    geometry = db.scalar(select(PCBGeometry).where(PCBGeometry.revision_id == revision.id))
    summary = revision.summary or {}
    return BoardSummary(
        design=DesignRef.model_validate(design),
        revision=svc.revision_out(db, revision),
        title=summary.get("title"),
        source=summary.get("source", {}),
        constraints=summary.get("constraints", {}),
        geometry=GeometryOut.model_validate(geometry) if geometry else None,
        stats=revision.object_counts,
        warnings=[WarningOut(**w) for w in revision.warnings],
    )


@router.get(
    "/{design_id}/normalized",
    responses={**error_responses(401, 404, 409, 503), 200: {"content": {"application/json": {}}}},
    response_class=Response,
)
def normalized_design(
    design_id: uuid.UUID, db: DB, storage: Storage, ctx: CurrentAuth, revision_id: uuid.UUID | None = None
) -> Response:
    """The complete normalized design (VIA's `PCBDesign` JSON), gzip-encoded on the wire."""
    design, _, _ = svc.get_design(db, ctx.user.id, design_id)
    revision = svc.resolve_parsed_revision(db, design, revision_id)
    file = db.scalar(
        select(DesignFile).where(DesignFile.revision_id == revision.id, DesignFile.kind == DesignFileKind.NORMALIZED)
    )
    if file is None:
        raise APIError(409, "not_parsed", "The parsed design is not available for this revision.")
    try:
        payload = storage.get(file.storage_key)
    except (ObjectNotFoundError, StorageError) as exc:
        raise APIError(503, "storage_unavailable", "The parsed design could not be loaded from storage.") from exc
    return Response(
        content=payload,
        media_type="application/json",
        headers={"Content-Encoding": "gzip", "Cache-Control": "private, no-store"},
    )


@router.get("/{design_id}/components", response_model=Page[ComponentOut], responses=error_responses(401, 404, 409))
def list_components(
    design_id: uuid.UUID,
    db: DB,
    ctx: CurrentAuth,
    revision_id: uuid.UUID | None = None,
    q: Annotated[str | None, Query(max_length=100, description="Reference, value or footprint")] = None,
    side: Annotated[str | None, Query(pattern="^(top|bottom)$")] = None,
    limit: Annotated[int, Query(ge=1, le=MAX_LIMIT)] = DEFAULT_LIMIT,
    offset: Annotated[int, Query(ge=0)] = 0,
) -> Page[ComponentOut]:
    design, _, _ = svc.get_design(db, ctx.user.id, design_id)
    revision = svc.resolve_parsed_revision(db, design, revision_id)
    conditions = [PCBComponent.revision_id == revision.id]
    if q and q.strip():
        pattern = f"%{_escape_like(q.strip())}%"
        conditions.append(
            PCBComponent.reference.ilike(pattern, escape="\\")
            | PCBComponent.value.ilike(pattern, escape="\\")
            | PCBComponent.footprint.ilike(pattern, escape="\\")
        )
    if side:
        conditions.append(PCBComponent.side == side)
    total = db.scalar(select(func.count(PCBComponent.id)).where(*conditions)) or 0
    # Natural order: R2 before R10 (prefix, then trailing number).
    prefix = func.regexp_replace(PCBComponent.reference, "[0-9]+$", "")
    number = cast(func.nullif(func.substring(PCBComponent.reference, "[0-9]+$"), ""), Integer)
    rows = db.scalars(
        select(PCBComponent)
        .where(*conditions)
        .order_by(prefix, number.nulls_first(), PCBComponent.reference, PCBComponent.id)
        .limit(limit)
        .offset(offset)
    )
    return Page[ComponentOut](
        items=[ComponentOut.model_validate(c) for c in rows], total=total, limit=limit, offset=offset
    )


@router.get("/{design_id}/nets", response_model=Page[NetOut], responses=error_responses(401, 404, 409))
def list_nets(
    design_id: uuid.UUID,
    db: DB,
    ctx: CurrentAuth,
    revision_id: uuid.UUID | None = None,
    q: Annotated[str | None, Query(max_length=100)] = None,
    limit: Annotated[int, Query(ge=1, le=MAX_LIMIT)] = DEFAULT_LIMIT,
    offset: Annotated[int, Query(ge=0)] = 0,
) -> Page[NetOut]:
    design, _, _ = svc.get_design(db, ctx.user.id, design_id)
    revision = svc.resolve_parsed_revision(db, design, revision_id)
    conditions = [PCBNet.revision_id == revision.id]
    if q and q.strip():
        conditions.append(PCBNet.name.ilike(f"%{_escape_like(q.strip())}%", escape="\\"))
    total = db.scalar(select(func.count(PCBNet.id)).where(*conditions)) or 0
    rows = db.scalars(
        select(PCBNet).where(*conditions).order_by(func.lower(PCBNet.name), PCBNet.id).limit(limit).offset(offset)
    )
    return Page[NetOut](items=[NetOut.model_validate(n) for n in rows], total=total, limit=limit, offset=offset)


@router.get("/{design_id}/layers", response_model=list[LayerOut], responses=error_responses(401, 404, 409))
def list_layers(design_id: uuid.UUID, db: DB, ctx: CurrentAuth, revision_id: uuid.UUID | None = None) -> list[LayerOut]:
    design, _, _ = svc.get_design(db, ctx.user.id, design_id)
    revision = svc.resolve_parsed_revision(db, design, revision_id)
    rows = db.scalars(select(PCBLayer).where(PCBLayer.revision_id == revision.id).order_by(PCBLayer.ordinal))
    return [LayerOut.model_validate(layer) for layer in rows]
