"""Cross-project views for the sidebar's Analysis and Components pages (read-only)."""

from __future__ import annotations

import uuid
from typing import Annotated

from fastapi import APIRouter, Query

from via_api.deps import DB, CurrentAuth
from via_api.errors import error_responses
from via_api.models.enums import AnalysisStatus
from via_api.schemas.browse import FindingListPage, FindingStatusFilter, PartListPage, PartSort, RunListPage
from via_api.schemas.common import DEFAULT_LIMIT, MAX_LIMIT
from via_api.services import access
from via_api.services import browse as svc
from via_pcb.analysis import Category, Severity

router = APIRouter(tags=["browse"])

Limit = Annotated[int, Query(ge=1, le=MAX_LIMIT)]
Offset = Annotated[int, Query(ge=0)]


def _check_project(db: DB, ctx: CurrentAuth, project_id: uuid.UUID | None) -> None:
    if project_id is not None:
        access.get_project(db, ctx.user.id, project_id)  # 404 if not accessible


@router.get("/analysis/runs", response_model=RunListPage, responses=error_responses(401, 404))
def browse_runs(
    db: DB,
    ctx: CurrentAuth,
    status_filter: Annotated[AnalysisStatus | None, Query(alias="status")] = None,
    project_id: uuid.UUID | None = None,
    include_archived: bool = False,
    limit: Limit = DEFAULT_LIMIT,
    offset: Offset = 0,
) -> RunListPage:
    """Analysis runs across every project you can view, newest first."""
    _check_project(db, ctx, project_id)
    return svc.browse_runs(
        db, ctx.user.id, status=status_filter, project_id=project_id, include_archived=include_archived,
        limit=limit, offset=offset,
    )  # fmt: skip


@router.get("/analysis/findings", response_model=FindingListPage, responses=error_responses(401, 404))
def browse_findings(
    db: DB,
    ctx: CurrentAuth,
    severity: Severity | None = None,
    category: Category | None = None,
    status_filter: Annotated[FindingStatusFilter, Query(alias="status")] = FindingStatusFilter.OPEN,
    q: Annotated[str | None, Query(max_length=100, description="Title or rule, or an exact component/net")] = None,
    project_id: uuid.UUID | None = None,
    include_archived: bool = False,
    limit: Limit = DEFAULT_LIMIT,
    offset: Offset = 0,
) -> FindingListPage:
    """Findings from each design's latest succeeded analysis, most severe first."""
    _check_project(db, ctx, project_id)
    return svc.browse_findings(
        db, ctx.user.id, severity=severity.value if severity else None, category=category.value if category else None,
        status=status_filter, q=q, project_id=project_id, include_archived=include_archived, limit=limit, offset=offset,
    )  # fmt: skip


@router.get("/components/parts", response_model=PartListPage, responses=error_responses(401, 404))
def browse_parts(
    db: DB,
    ctx: CurrentAuth,
    q: Annotated[str | None, Query(max_length=100, description="Value, footprint or reference")] = None,
    project_id: uuid.UUID | None = None,
    include_archived: bool = False,
    sort: PartSort = PartSort.PLACEMENTS,
    limit: Limit = DEFAULT_LIMIT,
    offset: Offset = 0,
) -> PartListPage:
    """Parts placed in the current revision of every design you can view, grouped by value and footprint."""
    _check_project(db, ctx, project_id)
    return svc.browse_parts(
        db, ctx.user.id, q=q, project_id=project_id, include_archived=include_archived, sort=sort,
        limit=limit, offset=offset,
    )  # fmt: skip
