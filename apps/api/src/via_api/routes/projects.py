"""/api/v1/projects: project CRUD, archive, members."""

from __future__ import annotations

import uuid
from typing import Annotated

from fastapi import APIRouter, Query, status

from via_api.deps import DB, Client, CurrentAuth, Limiter, Storage
from via_api.errors import error_responses
from via_api.models import User
from via_api.models.enums import ProjectRole
from via_api.ratelimit import MEMBER_LOOKUP_PER_USER
from via_api.schemas.common import DEFAULT_LIMIT, MAX_LIMIT, Page
from via_api.schemas.projects import (
    MemberAdd,
    MemberUpdate,
    ProjectCreate,
    ProjectMemberOut,
    ProjectOut,
    ProjectSort,
    ProjectStatusFilter,
    ProjectSummary,
    ProjectUpdate,
    UserRef,
)
from via_api.services import access
from via_api.services import designs as design_svc
from via_api.services import projects as svc

router = APIRouter(prefix="/projects", tags=["projects"])

NOT_FOUND = error_responses(401, 404)
FORBIDDEN = error_responses(401, 403, 404, 409)


@router.post("", response_model=ProjectOut, status_code=status.HTTP_201_CREATED, responses=error_responses(401, 404))
def create_project(body: ProjectCreate, db: DB, client: Client, ctx: CurrentAuth) -> ProjectOut:
    """Create a project. It is **private** unless `visibility` says otherwise."""
    project = svc.create(
        db,
        ctx,
        name=body.name,
        description=body.description,
        organization_id=body.organization_id,
        visibility=body.visibility,
        client=client,
    )
    db.commit()
    return svc.to_out(db, project, ProjectRole.OWNER, design_count=0)


@router.get("", response_model=Page[ProjectOut], responses=error_responses(401))
def list_projects(
    db: DB,
    ctx: CurrentAuth,
    q: Annotated[str | None, Query(max_length=100, description="Search name and description")] = None,
    status_filter: Annotated[ProjectStatusFilter, Query(alias="status")] = ProjectStatusFilter.ACTIVE,
    organization_id: uuid.UUID | None = None,
    sort: ProjectSort = ProjectSort.UPDATED,
    limit: Annotated[int, Query(ge=1, le=MAX_LIMIT)] = DEFAULT_LIMIT,
    offset: Annotated[int, Query(ge=0)] = 0,
) -> Page[ProjectOut]:
    """Projects you can access: owned, shared with you, or organization-visible in your organizations."""
    items, total = svc.list_for_user(
        db,
        ctx.user.id,
        q=q,
        status=status_filter,
        organization_id=organization_id,
        sort=sort,
        limit=limit,
        offset=offset,
    )
    return Page[ProjectOut](items=items, total=total, limit=limit, offset=offset)


@router.get("/summary", response_model=ProjectSummary, responses=error_responses(401))
def project_summary(db: DB, ctx: CurrentAuth) -> ProjectSummary:
    return svc.summary_for_user(db, ctx.user.id)


@router.get("/{project_id}", response_model=ProjectOut, responses=NOT_FOUND)
def get_project(project_id: uuid.UUID, db: DB, ctx: CurrentAuth) -> ProjectOut:
    project, role = access.get_project(db, ctx.user.id, project_id)
    return svc.to_out(db, project, role)


@router.patch("/{project_id}", response_model=ProjectOut, responses=FORBIDDEN)
def update_project(project_id: uuid.UUID, body: ProjectUpdate, db: DB, client: Client, ctx: CurrentAuth) -> ProjectOut:
    """Rename or edit the description (editor+); change visibility (owner)."""
    project, role = access.get_project(db, ctx.user.id, project_id, ProjectRole.EDITOR, action="edit details")
    svc.update(db, ctx, project, role, changes=body.model_dump(exclude_unset=True), client=client)
    db.commit()
    return svc.to_out(db, project, role)


@router.post("/{project_id}/archive", response_model=ProjectOut, responses=FORBIDDEN)
def archive_project(project_id: uuid.UUID, db: DB, client: Client, ctx: CurrentAuth) -> ProjectOut:
    project, role = access.get_project(db, ctx.user.id, project_id, ProjectRole.OWNER, action="archive projects")
    svc.set_archived(db, ctx, project, True, client)
    db.commit()
    return svc.to_out(db, project, role)


@router.post("/{project_id}/unarchive", response_model=ProjectOut, responses=FORBIDDEN)
def unarchive_project(project_id: uuid.UUID, db: DB, client: Client, ctx: CurrentAuth) -> ProjectOut:
    project, role = access.get_project(db, ctx.user.id, project_id, ProjectRole.OWNER, action="unarchive projects")
    svc.set_archived(db, ctx, project, False, client)
    db.commit()
    return svc.to_out(db, project, role)


@router.delete("/{project_id}", status_code=status.HTTP_204_NO_CONTENT, responses=FORBIDDEN)
def delete_project(project_id: uuid.UUID, db: DB, storage: Storage, client: Client, ctx: CurrentAuth) -> None:
    """Permanently delete a project and everything in it, including stored files (owner only)."""
    project, _ = access.get_project(db, ctx.user.id, project_id, ProjectRole.OWNER, action="delete projects")
    keys = design_svc.storage_keys(db, project_id=project.id)
    svc.delete(db, ctx, project, client)
    db.commit()
    design_svc.delete_objects(storage, keys)


@router.get("/{project_id}/members", response_model=list[ProjectMemberOut], responses=NOT_FOUND)
def list_members(project_id: uuid.UUID, db: DB, ctx: CurrentAuth) -> list[ProjectMemberOut]:
    project, _ = access.get_project(db, ctx.user.id, project_id)
    return svc.members(db, project)


@router.post(
    "/{project_id}/members",
    response_model=ProjectMemberOut,
    status_code=status.HTTP_201_CREATED,
    responses=error_responses(401, 403, 404, 409, 422, 429),
)
def add_member(
    project_id: uuid.UUID, body: MemberAdd, db: DB, client: Client, ctx: CurrentAuth, limiter: Limiter
) -> ProjectMemberOut:
    """Share the project with an existing VIA user by email (owner only)."""
    project, _ = access.get_project(db, ctx.user.id, project_id, ProjectRole.OWNER, action="manage members")
    limiter.hit(MEMBER_LOOKUP_PER_USER, str(ctx.user.id))
    member = svc.add_member(db, ctx, project, email=body.email, role=body.role, client=client)
    db.commit()
    return member


@router.patch("/{project_id}/members/{user_id}", response_model=ProjectMemberOut, responses=FORBIDDEN)
def update_member(
    project_id: uuid.UUID, user_id: uuid.UUID, body: MemberUpdate, db: DB, client: Client, ctx: CurrentAuth
) -> ProjectMemberOut:
    project, _ = access.get_project(db, ctx.user.id, project_id, ProjectRole.OWNER, action="manage members")
    m = svc.update_member(db, ctx, project, user_id, body.role, client)
    db.commit()
    user = db.get(User, user_id)
    return ProjectMemberOut(user=UserRef.model_validate(user), role=m.role, added_at=m.created_at)


@router.delete("/{project_id}/members/{user_id}", status_code=status.HTTP_204_NO_CONTENT, responses=FORBIDDEN)
def remove_member(project_id: uuid.UUID, user_id: uuid.UUID, db: DB, client: Client, ctx: CurrentAuth) -> None:
    """Remove a member (owner), or leave the project yourself (any member)."""
    minimum = ProjectRole.VIEWER if user_id == ctx.user.id else ProjectRole.OWNER
    project, _ = access.get_project(db, ctx.user.id, project_id, minimum, action="manage members")
    svc.remove_member(db, ctx, project, user_id, client)
    db.commit()
