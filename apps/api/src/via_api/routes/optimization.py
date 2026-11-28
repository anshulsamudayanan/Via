# ruff: noqa: E501
"""VIA Optimize (Stage 2, Milestone 5): runs, candidates, comparison, decisions. See docs/OPTIMIZATION_ENGINE.md."""

from __future__ import annotations

import uuid
from typing import Annotated, Any, Literal

from fastapi import APIRouter, Query, Response, status
from fastapi.responses import PlainTextResponse
from pydantic import BaseModel, Field, model_validator
from sqlalchemy import func, select
from via_opt import METRIC_FOR, MODULES, Constraints, ModuleSpec, Objective, dominates, lifecycle, pareto_front
from via_opt.report import build_report, render_markdown

from via_api.deps import DB, Client, CurrentAuth, Limiter, Queue
from via_api.errors import APIError, error_responses
from via_api.models import AnalysisRun, ChangeSet, DesignChange, DesignRevision, OptimizationCandidate
from via_api.models.enums import AnalysisKind, ChangeSetStatus, ConsentScope, ProjectRole
from via_api.ratelimit import ANALYSES_PER_USER
from via_api.schemas.analysis import AnalysisOptions
from via_api.services import access
from via_api.services import consent as consent_svc
from via_api.services import designs as design_svc
from via_api.services import optimizer as svc
from via_api.services.analysis import fail_run

router = APIRouter(tags=["optimization"])


class OptimizationStart(BaseModel):
    objectives: list[Objective] = Field(min_length=1, max_length=7)
    constraints: Constraints = Field(default_factory=Constraints)
    options: AnalysisOptions | None = None
    build_quantity: int | None = Field(
        default=None,
        ge=1,
        le=1_000_000,
        description="Boards you plan to build. When given, the BOM is priced from Mouser's live listings "
        "(needs the project owner's supplier consent). Without it no prices are looked up.",
    )
    weights: dict[Objective, float] | None = Field(
        default=None,
        description="Optional preference weights (>= 0) over the requested objectives. Order only: never changes validation.",
    )

    @model_validator(mode="after")
    def _weights_match_objectives(self) -> OptimizationStart:
        if self.weights:
            extra = set(self.weights) - set(self.objectives)
            if extra or any(not 0 <= w <= 1000 for w in self.weights.values()):
                raise ValueError("weights must be between 0 and 1000 and only for the requested objectives")
        return self


class OptimizationRunOut(BaseModel):
    id: uuid.UUID
    design_id: uuid.UUID
    revision_id: uuid.UUID
    revision_number: int
    status: str
    attempt: int
    config: dict[str, Any]
    summary: dict[str, Any]
    optimizer_version: str | None
    error_code: str | None
    error_message: str | None
    created_at: Any
    finished_at: Any


class ChangeOut(BaseModel):
    id: uuid.UUID
    ordinal: int
    kind: str
    target: dict[str, Any]
    before: dict[str, Any]
    after: dict[str, Any]
    reason: str
    source: str
    exportable: bool


class CandidateOut(BaseModel):
    id: uuid.UUID
    run_id: uuid.UUID
    key: str
    algorithm: str
    algorithm_version: str
    objectives: list[str]
    title: str
    summary: str
    metrics_before: dict[str, Any]
    metrics_after: dict[str, Any]
    expected_benefits: list[str]
    trade_offs: list[str]
    validation: dict[str, Any]
    pareto: bool
    status: str
    status_reason: str | None
    change_count: int
    exportable_changes: int
    # Added in optimizer 1.1.0 (older candidates have empty values)
    lifecycle: str
    constraints_evaluated: list[dict[str, Any]]
    warnings: list[str]
    limitations: list[str]
    execution: dict[str, Any]
    score: dict[str, Any] | None
    candidate_hash: str
    applied_revision: dict[str, Any] | None = Field(
        default=None, description="The revision a change set made from this candidate was applied as"
    )


class CandidateDetail(CandidateOut):
    changes: list[ChangeOut]
    details: dict[str, Any]


class Decision(BaseModel):
    status: Literal["accepted", "rejected"]
    reason: str | None = Field(default=None, max_length=2000)


class ComparisonOut(BaseModel):
    objectives: list[str]
    metrics: list[str]
    baseline: dict[str, Any]
    rows: list[dict[str, Any]] = Field(description="{candidate id, key, title, status, metrics, deltas}")
    pareto: list[uuid.UUID]
    dominance: dict[str, list[str]] = Field(description="Candidate id -> ids it dominates on the objectives")


def _run_out(db: DB, run: AnalysisRun) -> OptimizationRunOut:
    rev = db.get(DesignRevision, run.revision_id)
    assert rev is not None
    return OptimizationRunOut(id=run.id, design_id=rev.design_id, revision_id=rev.id, revision_number=rev.revision_number,
                              status=run.status.value, attempt=run.attempt, config=run.config or {}, summary=run.result_summary or {},
                              optimizer_version=run.analysis_version, error_code=run.error_code, error_message=run.error_message,
                              created_at=run.created_at, finished_at=run.finished_at)  # fmt: skip


def _counts(db: DB, cand_id: uuid.UUID) -> tuple[int, int]:
    total = db.scalar(select(func.count(DesignChange.id)).where(DesignChange.candidate_id == cand_id)) or 0
    exp = (
        db.scalar(
            select(func.count(DesignChange.id)).where(
                DesignChange.candidate_id == cand_id, DesignChange.exportable.is_(True)
            )
        )
        or 0
    )
    return total, exp


def _applied(db: DB, cand_id: uuid.UUID) -> dict[str, Any] | None:
    """The applied change set (and revision) made from this candidate, if any."""
    row = db.execute(
        select(ChangeSet.id, ChangeSet.result_revision_id)
        .join(DesignChange, DesignChange.change_set_id == ChangeSet.id)
        .where(DesignChange.origin_candidate_id == cand_id, ChangeSet.status == ChangeSetStatus.APPLIED)
        .order_by(ChangeSet.applied_at.desc())
        .limit(1)
    ).first()
    if row is None:
        return None
    rev = db.get(DesignRevision, row.result_revision_id) if row.result_revision_id else None
    return {"change_set_id": str(row.id), "revision_id": str(rev.id) if rev else None,
            "revision_number": rev.revision_number if rev else None}  # fmt: skip


def _cand_out(db: DB, c: OptimizationCandidate) -> CandidateOut:
    total, exp = _counts(db, c.id)
    applied = _applied(db, c.id)
    return CandidateOut(id=c.id, run_id=c.run_id, key=c.key, algorithm=c.algorithm, algorithm_version=c.algorithm_version,
                        objectives=list(c.objectives), title=c.title, summary=c.summary, metrics_before=c.metrics_before,
                        metrics_after=c.metrics_after, expected_benefits=c.expected_benefits, trade_offs=c.trade_offs,
                        validation=c.validation, pareto=c.pareto, status=c.status, status_reason=c.status_reason,
                        change_count=total, exportable_changes=exp,
                        lifecycle=lifecycle(c.status, str(c.validation.get("status", "")), c.status_reason, applied is not None),
                        constraints_evaluated=c.validation.get("constraints", []), warnings=c.warnings, limitations=c.limitations,
                        execution=c.execution, score=c.score, candidate_hash=c.candidate_hash, applied_revision=applied)  # fmt: skip


def _detail(db: DB, c: OptimizationCandidate) -> CandidateDetail:
    changes = db.scalars(
        select(DesignChange).where(DesignChange.candidate_id == c.id).order_by(DesignChange.ordinal)
    ).all()
    return CandidateDetail(**_cand_out(db, c).model_dump(), details=c.details,
                           changes=[ChangeOut(id=ch.id, ordinal=ch.ordinal, kind=ch.kind, target=ch.target, before=ch.before,
                                              after=ch.after, reason=ch.reason, source=ch.source, exportable=ch.exportable) for ch in changes])  # fmt: skip


class SupplierStatus(BaseModel):
    provider: str
    configured: bool = Field(description="A supplier key is set on this server")


class SupplierConsent(BaseModel):
    granted: bool
    granted_at: Any = None
    policy_version: str


@router.get("/suppliers/status", response_model=SupplierStatus, responses=error_responses(401))
def supplier_status(ctx: CurrentAuth) -> SupplierStatus:
    """Whether supplier pricing is set up on this server (it never reveals the key)."""
    return SupplierStatus(provider="mouser", configured=svc.supplier_factory() is not None)


def _consent_out(db: DB, project_id: uuid.UUID) -> SupplierConsent:
    row = consent_svc.active_consent(db, project_id, ConsentScope.SUPPLIER_LOOKUP)
    return SupplierConsent(
        granted=row is not None, granted_at=row.granted_at if row else None, policy_version=consent_svc.POLICY_VERSION
    )


@router.get(
    "/projects/{project_id}/supplier-consent", response_model=SupplierConsent, responses=error_responses(401, 404)
)
def get_supplier_consent(project_id: uuid.UUID, db: DB, ctx: CurrentAuth) -> SupplierConsent:
    project, _ = access.get_project(db, ctx.user.id, project_id)
    return _consent_out(db, project.id)


@router.put(
    "/projects/{project_id}/supplier-consent", response_model=SupplierConsent, responses=error_responses(401, 403, 404)
)
def grant_supplier_consent(project_id: uuid.UUID, db: DB, client: Client, ctx: CurrentAuth) -> SupplierConsent:
    """The project owner allows the design's manufacturer part numbers to be sent to Mouser for pricing."""
    project, _ = access.get_project(db, ctx.user.id, project_id, ProjectRole.OWNER, action="manage supplier lookups")
    consent_svc.grant(db, ctx, project.id, ConsentScope.SUPPLIER_LOOKUP, client)
    db.commit()
    return _consent_out(db, project.id)


@router.delete(
    "/projects/{project_id}/supplier-consent",
    status_code=status.HTTP_204_NO_CONTENT,
    responses=error_responses(401, 403, 404),
)
def revoke_supplier_consent(project_id: uuid.UUID, db: DB, client: Client, ctx: CurrentAuth) -> None:
    project, _ = access.get_project(db, ctx.user.id, project_id, ProjectRole.OWNER, action="manage supplier lookups")
    consent_svc.revoke(db, ctx, project.id, ConsentScope.SUPPLIER_LOOKUP, client)
    db.commit()


@router.get("/optimization-modules", response_model=list[ModuleSpec], responses=error_responses(401))
def list_modules(ctx: CurrentAuth) -> list[ModuleSpec]:
    """What each optimization module understands, requires, can't evaluate and preserves, and how complete it is."""
    return MODULES


@router.post("/designs/{design_id}/optimization-runs", response_model=OptimizationRunOut, status_code=status.HTTP_202_ACCEPTED,
             responses=error_responses(401, 403, 404, 409, 422, 429, 503))  # fmt: skip
def start_run(design_id: uuid.UUID, body: OptimizationStart, response: Response, db: DB, ctx: CurrentAuth, client: Client,
              limiter: Limiter, queue: Queue) -> OptimizationRunOut:  # fmt: skip
    """Generate, validate and compare candidates for the objectives, in the background. Never changes the design."""
    options = body.options.model_dump(exclude_none=True) if body.options else None
    run, created = svc.start(
        db, ctx, design_id, body.objectives, body.constraints, options, client, body.weights, body.build_quantity
    )
    if not created:
        response.status_code = status.HTTP_200_OK
        return _run_out(db, run)
    limiter.hit(ANALYSES_PER_USER, str(ctx.user.id))
    db.commit()
    try:
        queue.enqueue_optimization(run.id)
    except Exception as exc:
        fail_run(db, run, "queue_unavailable", "The optimization couldn't be started. Please try again.")
        db.commit()
        raise APIError(
            503, "queue_unavailable", "The optimization couldn't be started. Please try again shortly."
        ) from exc
    db.refresh(run)
    return _run_out(db, run)


@router.get(
    "/designs/{design_id}/optimization-runs",
    response_model=list[OptimizationRunOut],
    responses=error_responses(401, 404),
)
def list_runs(design_id: uuid.UUID, db: DB, ctx: CurrentAuth) -> list[OptimizationRunOut]:
    design, _, _ = design_svc.get_design(db, ctx.user.id, design_id)
    runs = db.scalars(select(AnalysisRun).join(DesignRevision, DesignRevision.id == AnalysisRun.revision_id)
                      .where(DesignRevision.design_id == design.id, AnalysisRun.kind == AnalysisKind.PCB_OPTIMIZATION)
                      .order_by(AnalysisRun.created_at.desc()).limit(50)).all()  # fmt: skip
    return [_run_out(db, r) for r in runs]


@router.get("/optimization-runs/{run_id}", response_model=OptimizationRunOut, responses=error_responses(401, 404))
def get_run(run_id: uuid.UUID, db: DB, ctx: CurrentAuth) -> OptimizationRunOut:
    return _run_out(db, svc.get_run(db, ctx.user.id, run_id))


@router.get(
    "/optimization-runs/{run_id}/candidates", response_model=list[CandidateOut], responses=error_responses(401, 404)
)
def list_candidates(run_id: uuid.UUID, db: DB, ctx: CurrentAuth) -> list[CandidateOut]:
    run = svc.get_run(db, ctx.user.id, run_id)
    rows = db.scalars(
        select(OptimizationCandidate).where(OptimizationCandidate.run_id == run.id).order_by(OptimizationCandidate.key)
    ).all()
    return [_cand_out(db, c) for c in rows]


@router.get(
    "/optimization-runs/{run_id}/compare", response_model=ComparisonOut, responses=error_responses(401, 404, 422)
)
def compare(run_id: uuid.UUID, db: DB, ctx: CurrentAuth,
            candidates: Annotated[str | None, Query(description="Comma-separated candidate ids (default: all)")] = None) -> ComparisonOut:  # fmt: skip
    """Side-by-side metrics and deltas vs the original, Pareto front and dominance over the run's objectives."""
    run = svc.get_run(db, ctx.user.id, run_id)
    stmt = select(OptimizationCandidate).where(OptimizationCandidate.run_id == run.id)
    if candidates:
        try:
            ids = [uuid.UUID(x) for x in candidates.split(",") if x.strip()]
        except ValueError:
            raise APIError(422, "invalid_filter", "candidates must be comma-separated ids.") from None
        stmt = stmt.where(OptimizationCandidate.id.in_(ids))
    rows = db.scalars(stmt.order_by(OptimizationCandidate.key)).all()
    objectives = run.config.get("objectives", [])
    keys = [METRIC_FOR[Objective(o)] for o in objectives]
    baseline = (run.result_summary or {}).get("baseline", {})
    metric_names = sorted({*baseline.keys()})
    points = {str(c.id): c.metrics_after for c in rows if c.metrics_after}
    front = pareto_front(points, keys) if points else []
    table = []
    for c in rows:
        deltas = {
            m: (c.metrics_after.get(m) - baseline[m])
            if c.metrics_after.get(m) is not None and baseline.get(m) is not None
            else None
            for m in metric_names
        }
        table.append(
            {
                "id": str(c.id),
                "key": c.key,
                "title": c.title,
                "status": c.status,
                "metrics": c.metrics_after,
                "deltas": deltas,
            }
        )
    dominance = {i: [j for j in points if j != i and dominates(points[i], points[j], keys)] for i in points}
    return ComparisonOut(
        objectives=objectives,
        metrics=metric_names,
        baseline=baseline,
        rows=table,
        pareto=[uuid.UUID(i) for i in front],
        dominance=dominance,
    )


@router.get("/optimization-runs/{run_id}/report", responses=error_responses(401, 404))
def report(run_id: uuid.UUID, db: DB, ctx: CurrentAuth,
           format: Annotated[Literal["json", "markdown"], Query(description="json (default) or a markdown document")] = "json") -> Any:  # fmt: skip
    """A summary of the run built from what was stored: calculated metrics only, what each candidate changes,
    which constraints were checked and which stayed unverified, and what 'validated' does not mean."""
    run = svc.get_run(db, ctx.user.id, run_id)
    rows = db.scalars(
        select(OptimizationCandidate).where(OptimizationCandidate.run_id == run.id).order_by(OptimizationCandidate.key)
    ).all()
    data = build_report(
        _run_out(db, run).model_dump(mode="json"), [_detail(db, c).model_dump(mode="json") for c in rows]
    )
    if format == "markdown":
        return PlainTextResponse(render_markdown(data), media_type="text/markdown; charset=utf-8")
    return data


@router.get(
    "/optimization-candidates/{candidate_id}", response_model=CandidateDetail, responses=error_responses(401, 404)
)
def get_candidate(candidate_id: uuid.UUID, db: DB, ctx: CurrentAuth) -> CandidateDetail:
    return _detail(db, svc.get_candidate(db, ctx.user.id, candidate_id))


@router.post(
    "/optimization-candidates/{candidate_id}/decision",
    response_model=CandidateDetail,
    responses=error_responses(401, 403, 404, 409, 422),
)
def decide(candidate_id: uuid.UUID, body: Decision, db: DB, ctx: CurrentAuth, client: Client) -> CandidateDetail:
    """Accept a validated candidate or reject one (reason required). The original design is not changed."""
    cand = svc.get_candidate(db, ctx.user.id, candidate_id, ProjectRole.EDITOR)
    svc.decide(db, ctx, cand, body.status, body.reason, client)
    db.commit()
    return _detail(db, cand)
