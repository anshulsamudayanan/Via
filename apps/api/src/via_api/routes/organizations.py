"""/api/v1/organizations: organizations you belong to.

Stage 1 scope: list, read, create a team organization, list members.
Invitations and organization role management come later. Organization roles
do not grant access to private projects (see services/access.py).
"""

from __future__ import annotations

import re
import secrets
import uuid

from fastapi import APIRouter, status
from sqlalchemy import select

from via_api.deps import DB, Client, CurrentAuth
from via_api.errors import error_responses, not_found
from via_api.models import Organization, OrganizationMembership, User
from via_api.models.enums import OrganizationRole
from via_api.schemas.projects import OrganizationCreate, OrganizationMemberOut, OrganizationOut, UserRef
from via_api.services import activity
from via_api.services.auth import organizations_for

router = APIRouter(prefix="/organizations", tags=["organizations"])


def _membership(db: DB, org_id: uuid.UUID, user_id: uuid.UUID) -> OrganizationMembership:
    m = db.scalar(
        select(OrganizationMembership).where(
            OrganizationMembership.organization_id == org_id, OrganizationMembership.user_id == user_id
        )
    )
    if m is None:
        raise not_found("Organization")
    return m


def _out(org: Organization, role: OrganizationRole) -> OrganizationOut:
    return OrganizationOut(
        id=org.id, name=org.name, slug=org.slug, is_personal=org.is_personal, role=role, created_at=org.created_at
    )


@router.get("", response_model=list[OrganizationOut], responses=error_responses(401))
def list_organizations(db: DB, ctx: CurrentAuth) -> list[OrganizationOut]:
    return [_out(org, role) for org, role in organizations_for(db, ctx.user.id)]


@router.post("", response_model=OrganizationOut, status_code=status.HTTP_201_CREATED, responses=error_responses(401))
def create_organization(body: OrganizationCreate, db: DB, client: Client, ctx: CurrentAuth) -> OrganizationOut:
    base = re.sub(r"[^a-z0-9]+", "-", body.name.lower()).strip("-")[:60] or "org"
    org = Organization(
        name=body.name, slug=f"{base}-{secrets.token_hex(3)}", is_personal=False, created_by_id=ctx.user.id
    )
    db.add(org)
    db.flush()
    db.add(OrganizationMembership(organization_id=org.id, user_id=ctx.user.id, role=OrganizationRole.OWNER))
    activity.record(
        db,
        activity.ORGANIZATION_CREATED,
        actor_id=ctx.user.id,
        client=client,
        organization_id=org.id,
        target_type="organization",
        target_id=org.id,
        details={"name": org.name},
    )
    db.commit()
    return _out(org, OrganizationRole.OWNER)


@router.get("/{organization_id}", response_model=OrganizationOut, responses=error_responses(401, 404))
def get_organization(organization_id: uuid.UUID, db: DB, ctx: CurrentAuth) -> OrganizationOut:
    m = _membership(db, organization_id, ctx.user.id)
    org = db.get(Organization, organization_id)
    assert org is not None
    return _out(org, m.role)


@router.get(
    "/{organization_id}/members", response_model=list[OrganizationMemberOut], responses=error_responses(401, 404)
)
def list_organization_members(organization_id: uuid.UUID, db: DB, ctx: CurrentAuth) -> list[OrganizationMemberOut]:
    _membership(db, organization_id, ctx.user.id)
    rows = db.execute(
        select(OrganizationMembership, User)
        .join(User, User.id == OrganizationMembership.user_id)
        .where(OrganizationMembership.organization_id == organization_id)
        .order_by(OrganizationMembership.created_at)
    ).all()
    return [OrganizationMemberOut(user=UserRef.model_validate(u), role=m.role, joined_at=m.created_at) for m, u in rows]
