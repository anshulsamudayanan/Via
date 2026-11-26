"""Cross-project read views: analysis runs, current findings and parts.

Every query is restricted to ``access.accessible_projects_clause`` and, unless asked otherwise, to
active (not archived) projects. Each view issues a fixed number of queries per page.
"""

from __future__ import annotations

import uuid
from typing import Any

from sqlalchemy import ColumnElement, distinct, func, or_, select
from sqlalchemy.dialects.postgresql import aggregate_order_by, distinct_on
from sqlalchemy.orm import Session

from via_api.models import AnalysisFinding, AnalysisRun, Design, DesignRevision, PCBComponent, Project, User
from via_api.models.enums import AnalysisKind, AnalysisStatus, FindingStatus
from via_api.schemas.browse import (
    FindingListItem,
    FindingListPage,
    FindingStatusFilter,
    NamedRef,
    PartListItem,
    PartListPage,
    PartSort,
    RunListItem,
    RunListPage,
)
from via_api.schemas.projects import ProjectRef, UserRef
from via_api.services import access

REFERENCE_SAMPLE = 12
DESIGN_SAMPLE = 5


def escape_like(term: str) -> str:
    return term.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")


def _scope(user_id: uuid.UUID, project_id: uuid.UUID | None, include_archived: bool) -> list[ColumnElement[bool]]:
    conditions = [access.accessible_projects_clause(user_id)]
    if not include_archived:
        conditions.append(Project.archived_at.is_(None))
    if project_id is not None:
        conditions.append(Project.id == project_id)
    return conditions


def _count(db: Session, query: Any) -> int:
    return db.scalar(select(func.count()).select_from(query.order_by(None).subquery())) or 0


# --------------------------------------------------------------------------- runs


def browse_runs(
    db: Session,
    user_id: uuid.UUID,
    *,
    status: AnalysisStatus | None,
    project_id: uuid.UUID | None,
    include_archived: bool,
    limit: int,
    offset: int,
) -> RunListPage:
    conditions = [*_scope(user_id, project_id, include_archived), AnalysisRun.kind == AnalysisKind.PCB_ANALYSIS]
    if status is not None:
        conditions.append(AnalysisRun.status == status)
    query = (
        select(AnalysisRun, DesignRevision, Design, Project, User)
        .join(DesignRevision, DesignRevision.id == AnalysisRun.revision_id)
        .join(Design, Design.id == DesignRevision.design_id)
        .join(Project, Project.id == AnalysisRun.project_id)
        .outerjoin(User, User.id == AnalysisRun.triggered_by_id)
        .where(*conditions)
    )
    total = _count(db, query)
    rows = db.execute(query.order_by(AnalysisRun.created_at.desc(), AnalysisRun.id).limit(limit).offset(offset)).all()
    items = []
    for run, rev, design, project, user in rows:
        summary = run.result_summary or {}
        succeeded = run.status == AnalysisStatus.SUCCEEDED
        items.append(
            RunListItem(
                id=run.id,
                status=run.status,
                design=NamedRef(id=design.id, name=design.name),
                project=ProjectRef.model_validate(project),
                project_archived=project.archived_at is not None,
                revision_id=rev.id,
                revision_number=rev.revision_number,
                finding_count=summary.get("finding_count") if succeeded else None,
                by_severity=summary.get("by_severity", {}) if succeeded else {},
                error_code=run.error_code,
                triggered_by=UserRef.model_validate(user) if user else None,
                created_at=run.created_at,
                finished_at=run.finished_at,
            )
        )
    return RunListPage(items=items, total=total, limit=limit, offset=offset)


# ----------------------------------------------------------------------- findings


def browse_findings(
    db: Session,
    user_id: uuid.UUID,
    *,
    severity: str | None,
    category: str | None,
    status: FindingStatusFilter,
    q: str | None,
    project_id: uuid.UUID | None,
    include_archived: bool,
    limit: int,
    offset: int,
) -> FindingListPage:
    """Findings of each design's latest succeeded analysis, most severe first."""
    latest = (
        select(AnalysisRun.id.label("run_id"), DesignRevision.design_id)
        .join(DesignRevision, DesignRevision.id == AnalysisRun.revision_id)
        .join(Project, Project.id == AnalysisRun.project_id)
        .where(
            *_scope(user_id, project_id, include_archived),
            AnalysisRun.kind == AnalysisKind.PCB_ANALYSIS,
            AnalysisRun.status == AnalysisStatus.SUCCEEDED,
        )
        .order_by(DesignRevision.design_id, AnalysisRun.created_at.desc(), AnalysisRun.id.desc())
        .ext(distinct_on(DesignRevision.design_id))
        .subquery()
    )
    designs_analysed = db.scalar(select(func.count()).select_from(latest)) or 0

    base: list[ColumnElement[bool]] = [AnalysisFinding.run_id.in_(select(latest.c.run_id))]
    if status != FindingStatusFilter.ALL:
        base.append(AnalysisFinding.status == FindingStatus(status.value))
    if category:
        base.append(AnalysisFinding.category == category)
    if q:
        pattern = f"%{escape_like(q.strip())}%"
        base.append(
            or_(
                AnalysisFinding.title.ilike(pattern, escape="\\"),
                AnalysisFinding.rule.ilike(pattern, escape="\\"),
                AnalysisFinding.components.contains([q.strip()]),
                AnalysisFinding.nets.contains([q.strip()]),
            )
        )
    by_severity = {
        str(sev): n
        for sev, n in db.execute(
            select(AnalysisFinding.severity, func.count()).where(*base).group_by(AnalysisFinding.severity)
        ).all()
    }
    conditions = [*base, AnalysisFinding.severity == severity] if severity else base
    query = (
        select(AnalysisFinding, DesignRevision.revision_number, Design.name, Project)
        .join(DesignRevision, DesignRevision.id == AnalysisFinding.revision_id)
        .join(Design, Design.id == AnalysisFinding.design_id)
        .join(Project, Project.id == AnalysisFinding.project_id)
        .where(*conditions)
    )
    total = _count(db, query)
    rows = db.execute(
        query.order_by(AnalysisFinding.severity_rank, Design.name, AnalysisFinding.title, AnalysisFinding.id)
        .limit(limit)
        .offset(offset)
    ).all()
    items = [
        FindingListItem(
            id=f.id,
            run_id=f.run_id,
            design=NamedRef(id=f.design_id, name=design_name),
            project=ProjectRef.model_validate(project),
            revision_id=f.revision_id,
            revision_number=number,
            check_id=f.check_id,
            rule=f.rule,
            category=f.category,
            severity=f.severity,
            source=f.source,
            verification=f.verification,
            title=f.title,
            status=f.status,
            components=list(f.components or [])[:8],
            nets=list(f.nets or [])[:8],
            created_at=f.created_at,
        )
        for f, number, design_name, project in rows
    ]
    return FindingListPage(
        items=items, total=total, limit=limit, offset=offset, by_severity=by_severity, designs_analysed=designs_analysed
    )


# -------------------------------------------------------------------------- parts


def browse_parts(
    db: Session,
    user_id: uuid.UUID,
    *,
    q: str | None,
    project_id: uuid.UUID | None,
    include_archived: bool,
    sort: PartSort,
    limit: int,
    offset: int,
) -> PartListPage:
    """Components of each design's current revision, grouped by (value, footprint)."""
    conditions = [*_scope(user_id, project_id, include_archived)]
    if q:
        pattern = f"%{escape_like(q.strip())}%"
        conditions.append(
            or_(
                PCBComponent.value.ilike(pattern, escape="\\"),
                PCBComponent.footprint.ilike(pattern, escape="\\"),
                PCBComponent.reference.ilike(pattern, escape="\\"),
            )
        )
    totals = db.execute(
        select(func.count(PCBComponent.id), func.count(distinct(Design.id)))
        .select_from(PCBComponent)
        .join(Design, Design.current_revision_id == PCBComponent.revision_id)
        .join(Project, Project.id == Design.project_id)
        .where(*conditions)
    ).one()
    placements = func.count(PCBComponent.id).label("placements")
    grouped = (
        select(
            PCBComponent.value,
            PCBComponent.footprint,
            placements,
            func.count(distinct(Design.id)).label("design_count"),
            func.array_agg(aggregate_order_by(PCBComponent.reference, PCBComponent.reference)).label("refs"),
            func.array_agg(distinct(Design.id)).label("design_ids"),
        )
        .select_from(PCBComponent)
        .join(Design, Design.current_revision_id == PCBComponent.revision_id)
        .join(Project, Project.id == Design.project_id)
        .where(*conditions)
        .group_by(PCBComponent.value, PCBComponent.footprint)
    )
    total = _count(db, grouped)
    order = {
        PartSort.PLACEMENTS: (placements.desc(), PCBComponent.value, PCBComponent.footprint),
        PartSort.VALUE: (func.lower(PCBComponent.value).asc().nulls_last(), PCBComponent.footprint),
        PartSort.FOOTPRINT: (func.lower(PCBComponent.footprint).asc(), PCBComponent.value),
    }[sort]
    rows = db.execute(grouped.order_by(*order).limit(limit).offset(offset)).all()
    wanted = {d for row in rows for d in row.design_ids[:DESIGN_SAMPLE]}
    names = {
        d.id: {"id": d.id, "name": d.name, "project_id": d.project_id}
        for d in db.scalars(select(Design).where(Design.id.in_(wanted)))
    }
    items = []
    for row in rows:
        refs = sorted(set(row.refs), key=_ref_key)
        items.append(
            PartListItem(
                value=row.value,
                footprint=row.footprint,
                placements=row.placements,
                design_count=row.design_count,
                references=refs[:REFERENCE_SAMPLE],
                references_truncated=len(refs) > REFERENCE_SAMPLE,
                designs=sorted(
                    (names[d] for d in row.design_ids[:DESIGN_SAMPLE] if d in names), key=lambda x: x["name"].lower()
                ),
            )
        )
    return PartListPage(
        items=items, total=total, limit=limit, offset=offset, placements=totals[0] or 0, designs=totals[1] or 0
    )


def _ref_key(ref: str) -> tuple[str, int, str]:
    """Natural order for reference designators: R2 before R10."""
    prefix = ref.rstrip("0123456789")
    digits = ref[len(prefix) :]
    return (prefix, int(digits) if digits.isdigit() else -1, ref)
