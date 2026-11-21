"""Project authorization: the single place that decides who may do what.

Rules (docs/DATABASE.md "Authorization model"):

* The project owner has ``owner``.
* An explicit ``project_memberships`` row grants its role.
* If the project's visibility is ``organization``, members of the owning
  organization get ``viewer``. Organization roles (even ``owner``/``admin``)
  never grant access to *private* projects.
* Everyone else has no access, and the project is reported as not found (404)
  so its existence isn't revealed.

Every route that touches project-scoped data must go through
:func:`get_project` (single object) or :func:`accessible_projects_clause`
(queries).
"""

from __future__ import annotations

import uuid

from sqlalchemy import ColumnElement, and_, exists, or_, select
from sqlalchemy.orm import Session

from via_api.errors import APIError, not_found
from via_api.models import OrganizationMembership, Project, ProjectMembership
from via_api.models.enums import ProjectRole, ProjectVisibility

_RANK = {ProjectRole.VIEWER: 1, ProjectRole.EDITOR: 2, ProjectRole.OWNER: 3}


def at_least(role: ProjectRole, minimum: ProjectRole) -> bool:
    return _RANK[role] >= _RANK[minimum]


def project_role(db: Session, user_id: uuid.UUID, project: Project) -> ProjectRole | None:
    if project.owner_id == user_id:
        return ProjectRole.OWNER
    membership = db.scalar(
        select(ProjectMembership.role).where(
            ProjectMembership.project_id == project.id, ProjectMembership.user_id == user_id
        )
    )
    if membership is not None:
        return membership
    if project.visibility == ProjectVisibility.ORGANIZATION and is_org_member(db, user_id, project.organization_id):
        return ProjectRole.VIEWER
    return None


def is_org_member(db: Session, user_id: uuid.UUID, organization_id: uuid.UUID) -> bool:
    return (
        db.scalar(
            select(OrganizationMembership.id).where(
                OrganizationMembership.organization_id == organization_id, OrganizationMembership.user_id == user_id
            )
        )
        is not None
    )


def accessible_projects_clause(user_id: uuid.UUID) -> ColumnElement[bool]:
    """SQL condition on ``Project`` matching exactly the projects ``user_id`` may view."""
    return or_(
        Project.owner_id == user_id,
        exists(
            select(ProjectMembership.id).where(
                ProjectMembership.project_id == Project.id, ProjectMembership.user_id == user_id
            )
        ),
        and_(
            Project.visibility == ProjectVisibility.ORGANIZATION,
            exists(
                select(OrganizationMembership.id).where(
                    OrganizationMembership.organization_id == Project.organization_id,
                    OrganizationMembership.user_id == user_id,
                )
            ),
        ),
    )


def get_project(
    db: Session,
    user_id: uuid.UUID,
    project_id: uuid.UUID,
    minimum: ProjectRole = ProjectRole.VIEWER,
    *,
    action: str = "do that",
) -> tuple[Project, ProjectRole]:
    """Load a project the user may access with at least ``minimum`` role.

    404 if the user can't see it at all; 403 if they can see it but lack the role.
    """
    project = db.get(Project, project_id)
    role = project_role(db, user_id, project) if project is not None else None
    if project is None or role is None:
        raise not_found("Project")
    if not at_least(role, minimum):
        raise APIError(403, "forbidden", f"You need the {minimum.value} role to {action} in this project.")
    return project, role


def ensure_active(project: Project) -> None:
    if project.archived_at is not None:
        raise APIError(409, "project_archived", "This project is archived. Unarchive it to make changes.")
