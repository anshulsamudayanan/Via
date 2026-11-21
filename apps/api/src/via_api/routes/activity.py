"""/api/v1/activity: activity feed.

You see activity on projects you can currently access, plus your own
account events (sign-ins, password changes...). IP addresses and user agents
are never included in the feed.
"""

from __future__ import annotations

import uuid
from typing import Annotated

from fastapi import APIRouter, Query
from sqlalchemy import and_, func, or_, select
from sqlalchemy.orm import aliased

from via_api.deps import DB, CurrentAuth
from via_api.errors import error_responses
from via_api.models import ActivityLog, Project, User
from via_api.schemas.common import DEFAULT_LIMIT, MAX_LIMIT, Page
from via_api.schemas.projects import ActivityOut, ProjectRef, UserRef
from via_api.services import access

router = APIRouter(prefix="/activity", tags=["activity"])


@router.get("", response_model=Page[ActivityOut], responses=error_responses(401, 404))
def list_activity(
    db: DB,
    ctx: CurrentAuth,
    project_id: uuid.UUID | None = None,
    limit: Annotated[int, Query(ge=1, le=MAX_LIMIT)] = DEFAULT_LIMIT,
    offset: Annotated[int, Query(ge=0)] = 0,
) -> Page[ActivityOut]:
    if project_id is not None:
        access.get_project(db, ctx.user.id, project_id)  # 404 if not accessible
        condition = ActivityLog.project_id == project_id
    else:
        accessible = select(Project.id).where(access.accessible_projects_clause(ctx.user.id))
        condition = or_(
            ActivityLog.project_id.in_(accessible),
            and_(ActivityLog.project_id.is_(None), ActivityLog.actor_id == ctx.user.id),
        )
    total = db.scalar(select(func.count(ActivityLog.id)).where(condition)) or 0
    actor = aliased(User)
    rows = db.execute(
        select(ActivityLog, actor, Project)
        .outerjoin(actor, actor.id == ActivityLog.actor_id)
        .outerjoin(Project, Project.id == ActivityLog.project_id)
        .where(condition)
        .order_by(ActivityLog.created_at.desc(), ActivityLog.id.desc())
        .limit(limit)
        .offset(offset)
    ).all()
    items = [
        ActivityOut(
            id=log.id,
            action=log.action,
            created_at=log.created_at,
            actor=UserRef.model_validate(user) if user else None,
            project=ProjectRef.model_validate(project) if project else None,
            target_type=log.target_type,
            target_id=log.target_id,
            details=log.details,
        )
        for log, user, project in rows
    ]
    return Page[ActivityOut](items=items, total=total, limit=limit, offset=offset)
