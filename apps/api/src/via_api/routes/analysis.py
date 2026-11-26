"""Analysis runs and findings (Stage 2). Every route enforces project access (404 when inaccessible)."""

from __future__ import annotations

import uuid
from typing import Annotated, Literal

from fastapi import APIRouter, Query, Response, status
from sqlalchemy import Select, func, or_, select

from via_api.deps import DB, Client, CurrentAuth, Limiter, Queue
from via_api.errors import APIError, error_responses, not_found
from via_api.models import AnalysisFinding, AnalysisRun, DesignRevision, FindingEvidence, FindingReviewEvent
from via_api.models.enums import FindingStatus, ProjectRole
from via_api.ratelimit import ANALYSES_PER_USER
from via_api.schemas.analysis import (
    AnalysisRunOut,
    AnalysisRunPage,
    AnalysisStart,
    CheckInfo,
    CheckRunOut,
    CompareOut,
    EvidenceOut,
    FindingDetail,
    FindingOut,
    FindingPage,
    ReviewEventOut,
    ReviewRequest,
)
from via_api.services import analysis as svc
from via_api.services import designs as design_svc
from via_pcb.analysis import Category, Severity, Source, Verification, default_registry

router = APIRouter(tags=["analysis"])


def run_out(db: DB, run: AnalysisRun) -> AnalysisRunOut:
    revision = db.get(DesignRevision, run.revision_id)
    assert revision is not None
    return AnalysisRunOut(
        id=run.id,
        design_id=revision.design_id,
        revision_id=revision.id,
        revision_number=revision.revision_number,
        status=run.status,
        attempt=run.attempt,
        config=run.config or {},
        checks=[CheckRunOut(**c) for c in run.checks or []],
        summary=run.result_summary or {},
        analysis_version=run.analysis_version,
        engine_version=run.engine_version,
        design_parser_version=run.design_parser_version,
        design_schema_version=run.design_schema_version,
        error_code=run.error_code,
        error_message=run.error_message,
        triggered_by=design_svc._user_ref(db, run.triggered_by_id),
        created_at=run.created_at,
        started_at=run.started_at,
        finished_at=run.finished_at,
    )


def finding_out(f: AnalysisFinding) -> FindingOut:
    return FindingOut.model_validate({**{c: getattr(f, c) for c in FindingOut.model_fields if c != "inherited"},
                                      "inherited": f.inherited_from_id is not None})  # fmt: skip


@router.get("/analysis/checks", response_model=list[CheckInfo], responses=error_responses(401))
def list_checks(ctx: CurrentAuth) -> list[CheckInfo]:
    """The checks VIA can run, with their versions and where their findings come from."""
    return [
        CheckInfo(
            id=c.id, version=c.version, category=c.category, title=c.title, description=c.description, source=c.source
        )
        for c in default_registry().all()
    ]


@router.post(
    "/designs/{design_id}/analysis-runs",
    response_model=AnalysisRunOut,
    status_code=status.HTTP_202_ACCEPTED,
    responses=error_responses(401, 403, 404, 409, 422, 429, 503),
)
def start_run(
    design_id: uuid.UUID,
    body: AnalysisStart,
    response: Response,
    db: DB,
    ctx: CurrentAuth,
    client: Client,
    limiter: Limiter,
    queue: Queue,
) -> AnalysisRunOut:
    """Analyse a parsed revision (default: the current one) in the background.

    Idempotent: if the same analysis is already queued or running for that revision, it is
    returned with `200` instead of starting another. Poll `GET /analysis-runs/{id}`.
    """
    run, created = svc.start_analysis(db, ctx, design_id, body.revision_id, body.checks, client)
    if not created:
        response.status_code = status.HTTP_200_OK
        return run_out(db, run)
    limiter.hit(ANALYSES_PER_USER, str(ctx.user.id))
    db.commit()
    try:
        queue.enqueue_analysis(run.id)
    except Exception as exc:
        svc.fail_run(db, run, "queue_unavailable", "The analysis couldn't be started. Please try again.")
        db.commit()
        raise APIError(503, "queue_unavailable", "The analysis couldn't be started. Please try again shortly.") from exc
    db.refresh(run)
    return run_out(db, run)


@router.get("/designs/{design_id}/analysis-runs", response_model=AnalysisRunPage, responses=error_responses(401, 404))
def list_runs(
    design_id: uuid.UUID,
    db: DB,
    ctx: CurrentAuth,
    limit: Annotated[int, Query(ge=1, le=100)] = 20,
    offset: Annotated[int, Query(ge=0)] = 0,
) -> AnalysisRunPage:
    """Analysis history of a design, newest first (all revisions)."""
    design, _, _ = design_svc.get_design(db, ctx.user.id, design_id)
    runs, total = svc.list_runs(db, design, limit, offset)
    return AnalysisRunPage(items=[run_out(db, r) for r in runs], total=total, limit=limit, offset=offset)


@router.get("/analysis-runs/{run_id}", response_model=AnalysisRunOut, responses=error_responses(401, 404))
def get_run(run_id: uuid.UUID, db: DB, ctx: CurrentAuth) -> AnalysisRunOut:
    return run_out(db, svc.get_run(db, ctx.user.id, run_id))


SortKey = Literal["severity", "category", "title", "check", "status", "confidence"]
_SORT = {
    "severity": AnalysisFinding.severity_rank,
    "category": AnalysisFinding.category,
    "title": AnalysisFinding.title,
    "check": AnalysisFinding.check_id,
    "status": AnalysisFinding.status,
    "confidence": AnalysisFinding.confidence,
}


def _csv(value: str | None, enum: type) -> list | None:
    if not value:
        return None
    try:
        return [enum(v.strip()) for v in value.split(",") if v.strip()]
    except ValueError as exc:
        raise APIError(422, "invalid_filter", f"Unknown value in filter: {exc}") from exc


def _escape_like(term: str) -> str:
    return term.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")


@router.get("/analysis-runs/{run_id}/findings", response_model=FindingPage, responses=error_responses(401, 404, 422))
def list_findings(
    run_id: uuid.UUID,
    db: DB,
    ctx: CurrentAuth,
    severity: Annotated[str | None, Query(description="Comma-separated, e.g. critical,high")] = None,
    category: str | None = None,
    source: str | None = None,
    verification: str | None = None,
    status_: Annotated[str | None, Query(alias="status", description="open, reviewed, dismissed")] = None,
    check_id: str | None = None,
    component: Annotated[str | None, Query(max_length=100, description="Reference designator")] = None,
    net: Annotated[str | None, Query(max_length=255)] = None,
    q: Annotated[str | None, Query(max_length=200, description="Search title, description, components, nets")] = None,
    sort: SortKey = "severity",
    order: Literal["asc", "desc"] = "asc",
    limit: Annotated[int, Query(ge=1, le=200)] = 50,
    offset: Annotated[int, Query(ge=0)] = 0,
) -> FindingPage:
    run = svc.get_run(db, ctx.user.id, run_id)
    stmt: Select = select(AnalysisFinding).where(AnalysisFinding.run_id == run.id)
    for column, values in (
        (AnalysisFinding.severity, _csv(severity, Severity)),
        (AnalysisFinding.category, _csv(category, Category)),
        (AnalysisFinding.source, _csv(source, Source)),
        (AnalysisFinding.verification, _csv(verification, Verification)),
        (AnalysisFinding.status, _csv(status_, FindingStatus)),
    ):
        if values:
            stmt = stmt.where(column.in_(values))
    if check_id:
        stmt = stmt.where(AnalysisFinding.check_id == check_id)
    if component:
        stmt = stmt.where(AnalysisFinding.components.contains([component]))
    if net:
        stmt = stmt.where(AnalysisFinding.nets.contains([net]))
    if q and q.strip():
        like = f"%{_escape_like(q.strip())}%"
        stmt = stmt.where(
            or_(
                AnalysisFinding.title.ilike(like, escape="\\"),
                AnalysisFinding.description.ilike(like, escape="\\"),
                func.array_to_string(AnalysisFinding.components, " ").ilike(like, escape="\\"),
                func.array_to_string(AnalysisFinding.nets, " ").ilike(like, escape="\\"),
            )
        )
    total = db.scalar(select(func.count()).select_from(stmt.subquery())) or 0
    key = _SORT[sort]
    stmt = stmt.order_by(
        key.desc() if order == "desc" else key.asc(), AnalysisFinding.severity_rank, AnalysisFinding.id
    )
    rows = db.scalars(stmt.limit(limit).offset(offset)).all()
    facets: dict[str, dict[str, int]] = {}
    for name, column in (
        ("severity", AnalysisFinding.severity),
        ("status", AnalysisFinding.status),
        ("category", AnalysisFinding.category),
        ("source", AnalysisFinding.source),
    ):
        counts = db.execute(select(column, func.count()).where(AnalysisFinding.run_id == run.id).group_by(column)).all()
        facets[name] = {str(getattr(k, "value", k)): n for k, n in counts}
    return FindingPage(items=[finding_out(f) for f in rows], total=total, limit=limit, offset=offset, facets=facets)


def finding_detail(db: DB, f: AnalysisFinding) -> FindingDetail:
    evidence = db.scalars(
        select(FindingEvidence).where(FindingEvidence.finding_id == f.id).order_by(FindingEvidence.ordinal)
    ).all()
    events = db.scalars(
        select(FindingReviewEvent).where(FindingReviewEvent.finding_id == f.id).order_by(FindingReviewEvent.created_at)
    ).all()
    history = [
        ReviewEventOut(
            from_status=e.from_status,
            to_status=e.to_status,
            reason=e.reason,
            carried_over=e.carried_over,
            actor=design_svc._user_ref(db, e.actor_id),
            created_at=e.created_at,
        )
        for e in events
    ]
    return FindingDetail(
        **finding_out(f).model_dump(), evidence=[EvidenceOut.model_validate(e) for e in evidence], history=history
    )


@router.get("/findings/{finding_id}", response_model=FindingDetail, responses=error_responses(401, 404))
def get_finding(finding_id: uuid.UUID, db: DB, ctx: CurrentAuth) -> FindingDetail:
    """A finding with its evidence and review history."""
    return finding_detail(db, svc.get_finding(db, ctx.user.id, finding_id))


@router.post(
    "/findings/{finding_id}/review", response_model=FindingDetail, responses=error_responses(401, 403, 404, 422)
)
def review_finding(
    finding_id: uuid.UUID, body: ReviewRequest, db: DB, ctx: CurrentAuth, client: Client
) -> FindingDetail:
    """Mark a finding reviewed, dismiss it (reason required) or reopen it. Every change is kept in its history."""
    finding = svc.get_finding(db, ctx.user.id, finding_id, ProjectRole.EDITOR)
    svc.review(db, ctx, finding, body.status, body.reason, client)
    db.commit()
    db.refresh(finding)
    return finding_detail(db, finding)


@router.get(
    "/designs/{design_id}/analysis-compare", response_model=CompareOut, responses=error_responses(401, 404, 409, 422)
)
def compare_runs(
    design_id: uuid.UUID, base_run_id: uuid.UUID, target_run_id: uuid.UUID, db: DB, ctx: CurrentAuth
) -> CompareOut:
    """Findings of two runs of this design matched by fingerprint: new in the target, resolved since the base,
    and persisting in both (listed as they appear in the target run)."""
    design, _, _ = design_svc.get_design(db, ctx.user.id, design_id)
    runs = []
    for rid in (base_run_id, target_run_id):
        run = svc.get_run(db, ctx.user.id, rid)
        revision = db.get(DesignRevision, run.revision_id)
        if revision is None or revision.design_id != design.id:
            raise not_found("Analysis run")
        runs.append(run)
    groups = svc.compare(db, runs[0], runs[1])
    return CompareOut(
        base_run=run_out(db, runs[0]),
        target_run=run_out(db, runs[1]),
        **{k: [finding_out(f) for f in v] for k, v in groups.items()},
    )
