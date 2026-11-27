"""Project lifecycle and membership."""

from __future__ import annotations

import uuid
from datetime import timedelta
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.dialects.postgresql import distinct_on
from sqlalchemy.orm import Session

from via_api.errors import APIError, not_found
from via_api.models import AnalysisRun, Design, DesignRevision, Organization, Project, ProjectMembership, User
from via_api.models.base import utcnow
from via_api.models.enums import AnalysisKind, AnalysisStatus, ProjectRole, ProjectVisibility
from via_api.schemas.projects import (
    LatestAnalysis,
    LatestImport,
    OrganizationRef,
    ProjectMemberOut,
    ProjectOut,
    ProjectSort,
    ProjectStatusFilter,
    ProjectSummary,
    UserRef,
)
from via_api.services import access, activity
from via_api.services.activity import ClientInfo
from via_api.services.auth import AuthContext


def _escape_like(term: str) -> str:
    return term.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")


def latest_work(
    db: Session, project_ids: list[uuid.UUID]
) -> tuple[dict[uuid.UUID, LatestImport], dict[uuid.UUID, LatestAnalysis]]:
    """Most recent upload and analysis run per project: two queries for any number of projects."""
    if not project_ids:
        return {}, {}
    imports = db.execute(
        select(DesignRevision, Design.name)
        .join(Design, Design.id == DesignRevision.design_id)
        .where(DesignRevision.project_id.in_(project_ids))
        .order_by(DesignRevision.project_id, DesignRevision.created_at.desc(), DesignRevision.id.desc())
        .ext(distinct_on(DesignRevision.project_id))
    ).all()
    analyses = db.execute(
        select(AnalysisRun, Design.id, Design.name)
        .join(DesignRevision, DesignRevision.id == AnalysisRun.revision_id)
        .join(Design, Design.id == DesignRevision.design_id)
        .where(AnalysisRun.project_id.in_(project_ids), AnalysisRun.kind == AnalysisKind.PCB_ANALYSIS)
        .order_by(AnalysisRun.project_id, AnalysisRun.created_at.desc(), AnalysisRun.id.desc())
        .ext(distinct_on(AnalysisRun.project_id))
    ).all()
    return (
        {
            rev.project_id: LatestImport(
                design_id=rev.design_id,
                design_name=name,
                revision_number=rev.revision_number,
                status=rev.status,
                at=rev.created_at,
            )
            for rev, name in imports
        },
        {
            run.project_id: LatestAnalysis(
                design_id=design_id,
                design_name=name,
                status=run.status,
                at=run.finished_at or run.created_at,
                finding_count=(
                    run.result_summary.get("finding_count") if run.status == AnalysisStatus.SUCCEEDED else None
                ),
                by_severity=(run.result_summary.get("by_severity") if run.status == AnalysisStatus.SUCCEEDED else None),
            )
            for run, design_id, name in analyses
        },
    )


def to_out(
    db: Session,
    project: Project,
    role: ProjectRole,
    design_count: int | None = None,
    latest: tuple[LatestImport | None, LatestAnalysis | None] | None = None,
) -> ProjectOut:
    org = db.get(Organization, project.organization_id)
    owner = db.get(User, project.owner_id)
    assert org is not None and owner is not None  # FKs guarantee both
    if design_count is None:
        design_count = db.scalar(select(func.count(Design.id)).where(Design.project_id == project.id)) or 0
    if latest is None:
        imports, analyses = latest_work(db, [project.id])
        latest = (imports.get(project.id), analyses.get(project.id))
    return ProjectOut(
        id=project.id,
        name=project.name,
        description=project.description,
        visibility=project.visibility,
        organization=OrganizationRef.model_validate(org),
        owner=UserRef.model_validate(owner),
        my_role=role,
        design_count=design_count,
        latest_import=latest[0],
        latest_analysis=latest[1],
        archived_at=project.archived_at,
        created_at=project.created_at,
        updated_at=project.updated_at,
    )


def personal_organization_id(db: Session, user_id: uuid.UUID) -> uuid.UUID:
    org_id = db.scalar(
        select(Organization.id).where(Organization.created_by_id == user_id, Organization.is_personal.is_(True))
    )
    if org_id is None:  # every registered user has one; defensive
        raise APIError(409, "no_personal_organization", "Your account has no personal workspace.")
    return org_id


def create(
    db: Session,
    ctx: AuthContext,
    *,
    name: str,
    description: str,
    organization_id: uuid.UUID | None,
    visibility: ProjectVisibility,
    client: ClientInfo,
) -> Project:
    org_id = organization_id or personal_organization_id(db, ctx.user.id)
    if not access.is_org_member(db, ctx.user.id, org_id):
        raise not_found("Organization")
    project = Project(
        organization_id=org_id, owner_id=ctx.user.id, name=name, description=description, visibility=visibility
    )
    db.add(project)
    db.flush()
    db.add(
        ProjectMembership(project_id=project.id, user_id=ctx.user.id, role=ProjectRole.OWNER, added_by_id=ctx.user.id)
    )
    activity.record(
        db,
        activity.PROJECT_CREATED,
        actor_id=ctx.user.id,
        client=client,
        project_id=project.id,
        organization_id=org_id,
        target_type="project",
        target_id=project.id,
        details={"name": name},
    )
    return project


def list_for_user(
    db: Session,
    user_id: uuid.UUID,
    *,
    q: str | None,
    status: ProjectStatusFilter,
    organization_id: uuid.UUID | None,
    sort: ProjectSort,
    limit: int,
    offset: int,
) -> tuple[list[ProjectOut], int]:
    conditions = [access.accessible_projects_clause(user_id)]
    if status == ProjectStatusFilter.ACTIVE:
        conditions.append(Project.archived_at.is_(None))
    elif status == ProjectStatusFilter.ARCHIVED:
        conditions.append(Project.archived_at.is_not(None))
    if organization_id is not None:
        conditions.append(Project.organization_id == organization_id)
    if q and q.strip():
        pattern = f"%{_escape_like(q.strip())}%"
        conditions.append(Project.name.ilike(pattern, escape="\\") | Project.description.ilike(pattern, escape="\\"))

    total = db.scalar(select(func.count(Project.id)).where(*conditions)) or 0
    order = {
        ProjectSort.UPDATED: Project.updated_at.desc(),
        ProjectSort.CREATED: Project.created_at.desc(),
        ProjectSort.NAME: func.lower(Project.name).asc(),
    }[sort]
    design_counts = select(Design.project_id, func.count(Design.id).label("n")).group_by(Design.project_id).subquery()
    rows = db.execute(
        select(Project, func.coalesce(design_counts.c.n, 0))
        .outerjoin(design_counts, design_counts.c.project_id == Project.id)
        .where(*conditions)
        .order_by(order, Project.id)
        .limit(limit)
        .offset(offset)
    ).all()
    imports, analyses = latest_work(db, [project.id for project, _ in rows])
    items = []
    for project, count in rows:
        role = access.project_role(db, user_id, project)
        assert role is not None  # guaranteed by accessible_projects_clause
        latest = (imports.get(project.id), analyses.get(project.id))
        items.append(to_out(db, project, role, design_count=count, latest=latest))
    return items, total


def summary_for_user(db: Session, user_id: uuid.UUID) -> ProjectSummary:
    accessible = access.accessible_projects_clause(user_id)
    base = select(func.count(Project.id)).where(accessible)
    active_ids = select(Project.id).where(accessible, Project.archived_at.is_(None))
    since = utcnow() - timedelta(days=7)
    return ProjectSummary(
        active=db.scalar(base.where(Project.archived_at.is_(None))) or 0,
        archived=db.scalar(base.where(Project.archived_at.is_not(None))) or 0,
        designs=db.scalar(select(func.count(Design.id)).where(Design.project_id.in_(active_ids))) or 0,
        imports_7d=db.scalar(
            select(func.count(DesignRevision.id)).where(
                DesignRevision.project_id.in_(active_ids), DesignRevision.created_at >= since
            )
        )
        or 0,
        analyses_7d=db.scalar(
            select(func.count(AnalysisRun.id)).where(
                AnalysisRun.project_id.in_(active_ids),
                AnalysisRun.kind == AnalysisKind.PCB_ANALYSIS,
                AnalysisRun.status.in_([AnalysisStatus.SUCCEEDED, AnalysisStatus.FAILED]),
                AnalysisRun.created_at >= since,
            )
        )
        or 0,
    )


def update(
    db: Session,
    ctx: AuthContext,
    project: Project,
    role: ProjectRole,
    *,
    changes: dict[str, Any],
    client: ClientInfo,
) -> Project:
    access.ensure_active(project)
    if "visibility" in changes and not access.at_least(role, ProjectRole.OWNER):
        raise APIError(403, "forbidden", "Only the project owner can change visibility.")
    applied: dict[str, Any] = {}
    for field, value in changes.items():
        if value is None or getattr(project, field) == value:
            continue
        if field == "name":
            applied["name"] = {"from": project.name, "to": value}
        else:
            applied[field] = True if field == "description" else {"from": getattr(project, field), "to": value}
        setattr(project, field, value)
    if applied:
        project.updated_at = utcnow()
        activity.record(
            db,
            activity.PROJECT_UPDATED,
            actor_id=ctx.user.id,
            client=client,
            project_id=project.id,
            organization_id=project.organization_id,
            target_type="project",
            target_id=project.id,
            details={"changes": applied},
        )
    return project


def set_archived(db: Session, ctx: AuthContext, project: Project, archived: bool, client: ClientInfo) -> Project:
    if archived == (project.archived_at is not None):
        return project
    project.archived_at = utcnow() if archived else None
    project.updated_at = utcnow()
    activity.record(
        db,
        activity.PROJECT_ARCHIVED if archived else activity.PROJECT_UNARCHIVED,
        actor_id=ctx.user.id,
        client=client,
        project_id=project.id,
        organization_id=project.organization_id,
        target_type="project",
        target_id=project.id,
    )
    return project


def delete(db: Session, ctx: AuthContext, project: Project, client: ClientInfo) -> None:
    # Audit entry survives the delete (project_id is SET NULL); keep the name for context.
    activity.record(
        db,
        activity.PROJECT_DELETED,
        actor_id=ctx.user.id,
        client=client,
        organization_id=project.organization_id,
        target_type="project",
        target_id=project.id,
        details={"name": project.name},
    )
    # Stored files are removed by the route after commit (services/designs.delete_objects).
    db.delete(project)


def members(db: Session, project: Project) -> list[ProjectMemberOut]:
    rows = db.execute(
        select(ProjectMembership, User)
        .join(User, User.id == ProjectMembership.user_id)
        .where(ProjectMembership.project_id == project.id)
        .order_by(ProjectMembership.created_at)
    ).all()
    return [ProjectMemberOut(user=UserRef.model_validate(user), role=m.role, added_at=m.created_at) for m, user in rows]


def add_member(
    db: Session, ctx: AuthContext, project: Project, *, email: str, role: ProjectRole, client: ClientInfo
) -> ProjectMemberOut:
    access.ensure_active(project)
    if role == ProjectRole.OWNER:
        raise APIError(422, "invalid_role", "A project has exactly one owner. Add members as editor or viewer.")
    user = db.scalar(select(User).where(User.email == email, User.is_active.is_(True)))
    if user is None:
        raise APIError(404, "user_not_found", "No VIA account uses that email address.")
    existing = db.scalar(
        select(ProjectMembership).where(
            ProjectMembership.project_id == project.id, ProjectMembership.user_id == user.id
        )
    )
    if existing is not None:
        raise APIError(409, "already_member", "That person is already a member of this project.")
    membership = ProjectMembership(project_id=project.id, user_id=user.id, role=role, added_by_id=ctx.user.id)
    db.add(membership)
    db.flush()
    activity.record(
        db,
        activity.PROJECT_MEMBER_ADDED,
        actor_id=ctx.user.id,
        client=client,
        project_id=project.id,
        target_type="user",
        target_id=user.id,
        details={"role": role.value, "member": user.display_name},
    )
    return ProjectMemberOut(user=UserRef.model_validate(user), role=role, added_at=membership.created_at)


def _membership(db: Session, project: Project, user_id: uuid.UUID) -> ProjectMembership:
    m = db.scalar(
        select(ProjectMembership).where(
            ProjectMembership.project_id == project.id, ProjectMembership.user_id == user_id
        )
    )
    if m is None:
        raise not_found("Member")
    return m


def update_member(
    db: Session, ctx: AuthContext, project: Project, user_id: uuid.UUID, role: ProjectRole, client: ClientInfo
) -> ProjectMembership:
    access.ensure_active(project)
    m = _membership(db, project, user_id)
    if user_id == project.owner_id or role == ProjectRole.OWNER:
        raise APIError(422, "invalid_role", "The owner's role can't be changed, and there can be only one owner.")
    if m.role != role:
        activity.record(
            db,
            activity.PROJECT_MEMBER_UPDATED,
            actor_id=ctx.user.id,
            client=client,
            project_id=project.id,
            target_type="user",
            target_id=user_id,
            details={"from": m.role.value, "to": role.value},
        )
        m.role = role
    return m


def remove_member(db: Session, ctx: AuthContext, project: Project, user_id: uuid.UUID, client: ClientInfo) -> None:
    if user_id == project.owner_id:
        raise APIError(422, "invalid_role", "The project owner can't be removed.")
    m = _membership(db, project, user_id)
    activity.record(
        db,
        activity.PROJECT_MEMBER_REMOVED,
        actor_id=ctx.user.id,
        client=client,
        project_id=project.id,
        target_type="user",
        target_id=user_id,
        details={"self": user_id == ctx.user.id},
    )
    db.delete(m)
