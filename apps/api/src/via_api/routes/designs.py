"""/api/v1/designs and /api/v1/revisions."""

from __future__ import annotations

import uuid

from fastapi import APIRouter, status

from via_api.deps import DB, Client, CurrentAuth, Storage
from via_api.errors import error_responses
from via_api.models.base import utcnow
from via_api.models.enums import ProjectRole
from via_api.schemas.pcb import DesignDetail, DesignOut, DesignUpdate, RevisionOut
from via_api.services import access, activity
from via_api.services import designs as svc

router = APIRouter(tags=["designs"])


@router.get("/designs", response_model=list[DesignOut], responses=error_responses(401, 404))
def list_designs(project_id: uuid.UUID, db: DB, ctx: CurrentAuth) -> list[DesignOut]:
    """Designs in a project, most recently updated first."""
    access.get_project(db, ctx.user.id, project_id)
    return svc.list_designs(db, project_id)


@router.get("/designs/{design_id}", response_model=DesignDetail, responses=error_responses(401, 404))
def get_design(design_id: uuid.UUID, db: DB, ctx: CurrentAuth) -> DesignDetail:
    design, _, _ = svc.get_design(db, ctx.user.id, design_id)
    return svc.design_detail(db, design)


@router.patch("/designs/{design_id}", response_model=DesignDetail, responses=error_responses(401, 403, 404, 409))
def update_design(design_id: uuid.UUID, body: DesignUpdate, db: DB, client: Client, ctx: CurrentAuth) -> DesignDetail:
    design, project, _ = svc.get_design(db, ctx.user.id, design_id, ProjectRole.EDITOR, action="edit designs")
    access.ensure_active(project)
    changes = body.model_dump(exclude_unset=True, exclude_none=True)
    if "description" in changes:
        changes["description"] = changes["description"].strip()
    changed = {k: v for k, v in changes.items() if getattr(design, k) != v}
    if changed:
        for k, v in changed.items():
            setattr(design, k, v)
        design.updated_at = utcnow()
        activity.record(
            db,
            svc.DESIGN_UPDATED,
            actor_id=ctx.user.id,
            client=client,
            project_id=design.project_id,
            target_type="design",
            target_id=design.id,
            details={"fields": sorted(changed), **({"name": changed["name"]} if "name" in changed else {})},
        )
        db.commit()
    return svc.design_detail(db, design)


@router.delete(
    "/designs/{design_id}", status_code=status.HTTP_204_NO_CONTENT, responses=error_responses(401, 403, 404, 409)
)
def delete_design(design_id: uuid.UUID, db: DB, storage: Storage, client: Client, ctx: CurrentAuth) -> None:
    """Delete a design, all its revisions, parsed data and stored files (editor+)."""
    design, project, _ = svc.get_design(db, ctx.user.id, design_id, ProjectRole.EDITOR, action="delete designs")
    access.ensure_active(project)
    keys = svc.delete_design(db, ctx, design, client)
    db.commit()
    svc.delete_objects(storage, keys)


@router.get("/revisions/{revision_id}", response_model=RevisionOut, responses=error_responses(401, 404))
def get_revision(revision_id: uuid.UUID, db: DB, ctx: CurrentAuth) -> RevisionOut:
    """One revision: processing status, parse warnings, object counts, or the failure reason."""
    revision, _ = svc.get_revision(db, ctx.user.id, revision_id)
    return svc.revision_out(db, revision)
