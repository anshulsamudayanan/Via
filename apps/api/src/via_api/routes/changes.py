# ruff: noqa: E501
"""Change management (Stage 2, Milestone 6): change sets, export, lineage, rollback, comparison.

See docs/CHANGE_MANAGEMENT.md.
"""

from __future__ import annotations

import uuid
from typing import Any

from fastapi import APIRouter, Response, status
from pydantic import BaseModel, Field
from sqlalchemy import select

from via_api.deps import DB, Client, CurrentAuth, Limiter, Queue, Storage
from via_api.errors import APIError, error_responses, not_found
from via_api.models import ChangeSet, DesignRevision
from via_api.models.enums import ProjectRole
from via_api.parsing.importer import source_file
from via_api.ratelimit import ANALYSES_PER_USER
from via_api.services import changes as svc
from via_api.services import designs as design_svc
from via_api.storage import ObjectNotFoundError, StorageError

router = APIRouter(tags=["changes"])


class ChangeIn(BaseModel):
    kind: str = Field(
        description="move_component | rotate_component | set_track_width | move_via | set_via_size | set_outline_rect"
    )
    target: dict[str, Any] = Field(description="{kind, id, label?}: the object's stable id from the normalized design")
    after: dict[str, Any]
    reason: str | None = Field(default=None, max_length=2000)


class ChangeSetCreate(BaseModel):
    title: str | None = Field(default=None, max_length=200)
    candidate_ids: list[uuid.UUID] = Field(default_factory=list, max_length=50)
    changes: list[ChangeIn] = Field(default_factory=list, max_length=svc.MAX_CHANGES)


class SetChangeOut(BaseModel):
    id: uuid.UUID
    ordinal: int
    kind: str
    target: dict[str, Any]
    before: dict[str, Any]
    after: dict[str, Any]
    reason: str
    source: str
    origin_candidate_id: uuid.UUID | None
    status: str
    status_reason: str | None


class ChangeSetOut(BaseModel):
    id: uuid.UUID
    design_id: uuid.UUID
    base_revision_id: uuid.UUID
    result_revision_id: uuid.UUID | None
    export_run_id: uuid.UUID | None
    title: str
    status: str
    result: dict[str, Any]
    error_code: str | None
    error_message: str | None
    created_at: Any
    applied_at: Any
    rolled_back_at: Any
    changes: list[SetChangeOut]


def _out(db: DB, cs: ChangeSet) -> ChangeSetOut:
    rows = svc.changes_of(db, cs)
    return ChangeSetOut(
        id=cs.id, design_id=cs.design_id, base_revision_id=cs.base_revision_id, result_revision_id=cs.result_revision_id,
        export_run_id=cs.export_run_id, title=cs.title, status=cs.status.value, result=cs.result or {}, error_code=cs.error_code,
        error_message=cs.error_message, created_at=cs.created_at, applied_at=cs.applied_at, rolled_back_at=cs.rolled_back_at,
        changes=[SetChangeOut(id=r.id, ordinal=r.ordinal, kind=r.kind, target=r.target, before=r.before, after=r.after, reason=r.reason,
                              source=r.source, origin_candidate_id=r.origin_candidate_id, status=r.status.value, status_reason=r.status_reason)
                 for r in rows],
    )  # fmt: skip


@router.post("/designs/{design_id}/change-sets", response_model=ChangeSetOut, status_code=status.HTTP_201_CREATED,
             responses=error_responses(401, 403, 404, 409, 422))  # fmt: skip
def create_change_set(
    design_id: uuid.UUID, body: ChangeSetCreate, db: DB, storage: Storage, ctx: CurrentAuth, client: Client
) -> ChangeSetOut:
    """Collect accepted candidates' changes and/or your own changes against the current revision. Nothing is applied yet."""
    cs = svc.create(db, storage, ctx, design_id, title=body.title, candidate_ids=body.candidate_ids,
                    user_changes=[c.model_dump() for c in body.changes], client=client)  # fmt: skip
    db.commit()
    return _out(db, cs)


@router.get("/designs/{design_id}/change-sets", response_model=list[ChangeSetOut], responses=error_responses(401, 404))
def list_change_sets(design_id: uuid.UUID, db: DB, ctx: CurrentAuth) -> list[ChangeSetOut]:
    """Change history of the design, newest first."""
    design, _, _ = design_svc.get_design(db, ctx.user.id, design_id)
    rows = db.scalars(
        select(ChangeSet).where(ChangeSet.design_id == design.id).order_by(ChangeSet.created_at.desc()).limit(100)
    ).all()
    return [_out(db, cs) for cs in rows]


@router.get("/designs/{design_id}/lineage", response_model=list[dict[str, Any]], responses=error_responses(401, 404))
def design_lineage(design_id: uuid.UUID, db: DB, ctx: CurrentAuth) -> list[dict[str, Any]]:
    """Every revision with its parent and the change set that produced it."""
    design, _, _ = design_svc.get_design(db, ctx.user.id, design_id)
    return svc.lineage(db, design.id)


@router.get("/change-sets/{change_set_id}", response_model=ChangeSetOut, responses=error_responses(401, 404))
def get_change_set(change_set_id: uuid.UUID, db: DB, ctx: CurrentAuth) -> ChangeSetOut:
    return _out(db, svc.get_change_set(db, ctx.user.id, change_set_id))


@router.get(
    "/change-sets/{change_set_id}/preview", response_model=dict[str, Any], responses=error_responses(401, 404, 503)
)
def preview_change_set(change_set_id: uuid.UUID, db: DB, storage: Storage, ctx: CurrentAuth) -> dict[str, Any]:
    """Metrics before and after, computed on VIA's model with the changes applied (simulated, not the exported file)."""
    cs = svc.get_change_set(db, ctx.user.id, change_set_id)
    try:
        return svc.preview(db, storage, cs)
    except (ObjectNotFoundError, StorageError) as exc:
        raise APIError(503, "design_unavailable", "The parsed design couldn't be loaded.") from exc


@router.delete("/change-sets/{change_set_id}/changes/{change_id}", status_code=status.HTTP_204_NO_CONTENT,
               responses=error_responses(401, 403, 404, 409))  # fmt: skip
def remove_change(change_set_id: uuid.UUID, change_id: uuid.UUID, db: DB, ctx: CurrentAuth) -> Response:
    """Remove (undo) one change from a draft change set."""
    cs = svc.get_change_set(db, ctx.user.id, change_set_id, ProjectRole.EDITOR)
    svc.remove_change(db, cs, change_id)
    db.commit()
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.delete(
    "/change-sets/{change_set_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    responses=error_responses(401, 403, 404, 409),
)
def discard_change_set(change_set_id: uuid.UUID, db: DB, ctx: CurrentAuth, client: Client) -> Response:
    cs = svc.get_change_set(db, ctx.user.id, change_set_id, ProjectRole.EDITOR)
    svc.discard(db, ctx, cs, client)
    db.commit()
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.post("/change-sets/{change_set_id}/apply", response_model=ChangeSetOut, status_code=status.HTTP_202_ACCEPTED,
             responses=error_responses(401, 403, 404, 409, 422, 429, 503))  # fmt: skip
def apply_change_set(
    change_set_id: uuid.UUID, db: DB, ctx: CurrentAuth, client: Client, limiter: Limiter, queue: Queue
) -> ChangeSetOut:
    """Patch the original file with these changes, verify it and import it as a new revision (background job)."""
    cs = svc.get_change_set(db, ctx.user.id, change_set_id, ProjectRole.EDITOR)
    run = svc.request_apply(db, ctx, cs, client)
    limiter.hit(ANALYSES_PER_USER, str(ctx.user.id))
    db.commit()
    try:
        queue.enqueue_export(run.id)
    except Exception as exc:
        svc.fail_change_set(db, cs, run, "queue_unavailable", "The export couldn't be started. Please try again.")
        db.commit()
        raise APIError(503, "queue_unavailable", "The export couldn't be started. Please try again shortly.") from exc
    db.refresh(cs)
    return _out(db, cs)


@router.post(
    "/change-sets/{change_set_id}/rollback", response_model=ChangeSetOut, responses=error_responses(401, 403, 404, 409)
)
def rollback_change_set(change_set_id: uuid.UUID, db: DB, ctx: CurrentAuth, client: Client) -> ChangeSetOut:
    """Make the base revision current again. The exported revision stays in the history."""
    cs = svc.get_change_set(db, ctx.user.id, change_set_id, ProjectRole.EDITOR)
    svc.rollback(db, ctx, cs, client)
    db.commit()
    return _out(db, cs)


@router.get("/change-sets/{change_set_id}/download", responses=error_responses(401, 404, 409, 503))
def download_export(change_set_id: uuid.UUID, db: DB, storage: Storage, ctx: CurrentAuth) -> Response:
    """The exported file: your original upload with only the changed objects edited."""
    cs = svc.get_change_set(db, ctx.user.id, change_set_id)
    rev = db.get(DesignRevision, cs.result_revision_id) if cs.result_revision_id else None
    file = source_file(db, rev) if rev else None
    if file is None:
        raise APIError(409, "not_exported", "This change set hasn't been applied yet.")
    try:
        data = storage.get(file.storage_key)
    except ObjectNotFoundError as exc:
        raise not_found("File") from exc
    except StorageError as exc:
        raise APIError(503, "storage_unavailable", "File storage is unavailable.") from exc
    name = (file.original_filename or "board.kicad_pcb").replace('"', "")
    return Response(content=data, media_type="application/octet-stream",
                    headers={"Content-Disposition": f'attachment; filename="{name}"', "X-Content-Type-Options": "nosniff"})  # fmt: skip


@router.get("/designs/{design_id}/compare", response_model=dict[str, Any], responses=error_responses(401, 404, 422))
def compare_revisions(
    design_id: uuid.UUID, base: uuid.UUID, head: uuid.UUID, db: DB, ctx: CurrentAuth
) -> dict[str, Any]:
    """Object counts and findings (matched by fingerprint, from each revision's latest analysis) of two revisions."""
    design, _, _ = design_svc.get_design(db, ctx.user.id, design_id)
    revs = {
        r.id: r
        for r in db.scalars(
            select(DesignRevision).where(DesignRevision.design_id == design.id, DesignRevision.id.in_([base, head]))
        )
    }
    if base not in revs or head not in revs:
        raise not_found("Revision")
    return svc.compare_revisions(db, revs[base], revs[head])
