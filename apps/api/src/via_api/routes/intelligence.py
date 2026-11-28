# ruff: noqa: E501
"""VIA Intelligence (Stage 2, Milestone 4): AI explanations, design reviews, recommendations,
component records. AI output is always an unverified suggestion; see docs/AI_INTELLIGENCE.md."""

from __future__ import annotations

import uuid
from typing import Annotated, Any, Literal

from fastapi import APIRouter, Depends, Query, Response, status
from pydantic import BaseModel, Field
from sqlalchemy import func, or_, select

from via_ai import AIProvider
from via_api.ai import get_ai_provider
from via_api.deps import DB, Client, CurrentAuth, Limiter
from via_api.errors import APIError, error_responses, not_found
from via_api.models import AIOutput, AnalysisFinding, ComponentRecord, PCBComponent, RecommendationRow
from via_api.models.enums import FeedbackType, ProjectRole
from via_api.ratelimit import AI_REQUESTS_PER_USER
from via_api.services import access, components, learn
from via_api.services import designs as design_svc
from via_api.services import feedback as feedback_svc
from via_api.services import intelligence as svc

router = APIRouter(tags=["intelligence"])
Provider = Annotated[AIProvider, Depends(get_ai_provider)]


class Focus(BaseModel):
    kind: Literal["finding", "component", "net", "region"]
    id: str = Field(min_length=1, max_length=200, description="Finding id, reference, net name or 'x1,y1,x2,y2' (mm)")


class ExplainRequest(BaseModel):
    question: str = Field(min_length=1, max_length=2000)
    focus: Focus | None = None
    run_id: uuid.UUID | None = None


class FindingExplainRequest(BaseModel):
    question: str = Field(default="Why does this matter, and what should I do about it?", min_length=1, max_length=2000)


class ReviewRequest(BaseModel):
    run_id: uuid.UUID | None = None


class KnowledgeUsedOut(BaseModel):
    """A VIA Learn entry the model was shown, with attribution. `cited` entries are the only ones shown to have
    influenced the answer; the rest were retrieved but not used."""

    entry_id: uuid.UUID
    version: int
    title: str
    category: str
    verification_status: str
    source: str
    status: str
    cited: bool


class AIOutputOut(BaseModel):
    id: uuid.UUID
    kind: str
    source: str = Field(default="ai_suggestion", description="Always ai_suggestion: never a verified result")
    verification: str = Field(default="unverified")
    question: str | None
    focus: dict[str, Any] | None
    output: dict[str, Any]
    grounding: dict[str, Any] = Field(description="VIA's check that every cited object and number exists in the design")
    provider: str
    model: str
    prompt_version: str
    analysis_run_id: uuid.UUID | None
    revision_id: uuid.UUID
    created_at: Any
    knowledge: list[KnowledgeUsedOut] = Field(default_factory=list)


class RecommendationOut(BaseModel):
    id: uuid.UUID
    ai_output_id: uuid.UUID
    design_id: uuid.UUID
    revision_id: uuid.UUID
    source: str = "ai_suggestion"
    verification: str = "unverified"
    problem: str
    proposed_change: str
    rationale: str
    expected_benefits: list[str]
    trade_offs: list[str]
    required_validation: list[str]
    uncertainty: str
    references: list[dict[str, Any]]
    numbers_used: list[dict[str, Any]]
    evidence_finding_ids: list[str]
    confidence: str
    status: str
    status_reason: str | None
    created_at: Any
    knowledge: list[KnowledgeUsedOut] = Field(default_factory=list)


class ReviewOut(BaseModel):
    review: AIOutputOut
    recommendations: list[RecommendationOut]


class RecommendationUpdate(BaseModel):
    status: Literal["open", "accepted", "rejected"]
    reason: str | None = Field(default=None, max_length=2000)


def _out(row: AIOutput, db: Any) -> AIOutputOut:
    return AIOutputOut(id=row.id, kind=row.kind, question=row.question, focus=row.focus, output=row.output,
                       grounding=row.verification, provider=row.provider, model=row.model,
                       prompt_version=row.prompt_version, analysis_run_id=row.analysis_run_id,
                       revision_id=row.revision_id, created_at=row.created_at,
                       knowledge=[KnowledgeUsedOut(**k) for k in learn.knowledge_used(db, [row.id])[row.id]])  # fmt: skip


def _rec(r: RecommendationRow, knowledge: dict[uuid.UUID, list[dict[str, Any]]]) -> RecommendationOut:
    d = r.details or {}
    return RecommendationOut(
        id=r.id, ai_output_id=r.ai_output_id, design_id=r.design_id, revision_id=r.revision_id, problem=r.problem,
        proposed_change=r.proposed_change, rationale=r.rationale, expected_benefits=d.get("expected_benefits", []),
        trade_offs=d.get("trade_offs", []), required_validation=d.get("required_validation", []),
        uncertainty=d.get("uncertainty", ""), references=d.get("references", []), numbers_used=d.get("numbers_used", []),
        evidence_finding_ids=list(r.evidence_finding_ids), confidence=r.confidence, status=r.status,
        status_reason=r.status_reason, created_at=r.created_at, knowledge=[KnowledgeUsedOut(**k) for k in knowledge.get(r.ai_output_id, [])],
    )  # fmt: skip


@router.post("/designs/{design_id}/ai/explain", response_model=AIOutputOut,
             responses=error_responses(401, 403, 404, 409, 422, 429, 502, 503))  # fmt: skip
def explain_design(design_id: uuid.UUID, body: ExplainRequest, db: DB, ctx: CurrentAuth, client: Client,
                   limiter: Limiter, provider: Provider) -> AIOutputOut:  # fmt: skip
    """Ask about the design, optionally focused on a finding, component, net or region. Uses the latest
    analysis findings. External providers need the project owner's consent (`403 consent_required`)."""
    design_svc.get_design(db, ctx.user.id, design_id)  # 404 before spending rate limit
    limiter.hit(AI_REQUESTS_PER_USER, str(ctx.user.id))
    focus = (body.focus.kind, body.focus.id) if body.focus else None
    row = svc.explain_design(db, ctx, provider, design_id, body.question, focus, body.run_id, client)
    db.commit()
    return _out(row, db)


@router.post("/findings/{finding_id}/explain", response_model=AIOutputOut,
             responses=error_responses(401, 403, 404, 409, 422, 429, 502, 503))  # fmt: skip
def explain_finding(finding_id: uuid.UUID, body: FindingExplainRequest, db: DB, ctx: CurrentAuth, client: Client,
                    limiter: Limiter, provider: Provider) -> AIOutputOut:  # fmt: skip
    from via_api.services.analysis import get_finding

    finding: AnalysisFinding = get_finding(db, ctx.user.id, finding_id)
    limiter.hit(AI_REQUESTS_PER_USER, str(ctx.user.id))
    row = svc.explain_design(db, ctx, provider, finding.design_id, body.question, ("finding", str(finding.id)),
                             finding.run_id, client)  # fmt: skip
    db.commit()
    return _out(row, db)


@router.post("/designs/{design_id}/ai/review", response_model=ReviewOut,
             responses=error_responses(401, 403, 404, 409, 422, 429, 502, 503))  # fmt: skip
def review_design(design_id: uuid.UUID, body: ReviewRequest, db: DB, ctx: CurrentAuth, client: Client,
                  limiter: Limiter, provider: Provider) -> ReviewOut:  # fmt: skip
    """A structured AI design review over the latest analysis; recommendations are stored (editor)."""
    _, project, _ = design_svc.get_design(db, ctx.user.id, design_id, ProjectRole.EDITOR, action="request AI reviews")
    access.ensure_active(project)
    limiter.hit(AI_REQUESTS_PER_USER, str(ctx.user.id))
    row, recs = svc.review_design(db, ctx, provider, design_id, body.run_id, client)
    db.commit()
    know = learn.knowledge_used(db, [row.id])
    return ReviewOut(review=_out(row, db), recommendations=[_rec(r, know) for r in recs])


@router.get(
    "/designs/{design_id}/recommendations", response_model=list[RecommendationOut], responses=error_responses(401, 404)
)
def list_recommendations(
    design_id: uuid.UUID,
    db: DB,
    ctx: CurrentAuth,
    status_: Annotated[Literal["open", "accepted", "rejected"] | None, Query(alias="status")] = None,
) -> list[RecommendationOut]:
    design_svc.get_design(db, ctx.user.id, design_id)
    stmt = select(RecommendationRow).where(RecommendationRow.design_id == design_id)
    if status_:
        stmt = stmt.where(RecommendationRow.status == status_)
    rows = list(db.scalars(stmt.order_by(RecommendationRow.created_at.desc()).limit(200)))
    know = learn.knowledge_used(db, list({r.ai_output_id for r in rows}))
    return [_rec(r, know) for r in rows]


@router.patch(
    "/recommendations/{recommendation_id}",
    response_model=RecommendationOut,
    responses=error_responses(401, 403, 404, 422),
)
def update_recommendation(
    recommendation_id: uuid.UUID, body: RecommendationUpdate, db: DB, ctx: CurrentAuth
) -> RecommendationOut:
    """Record a decision on an AI suggestion (accepting it doesn't change the design)."""
    rec = db.get(RecommendationRow, recommendation_id)
    if rec is None:
        raise not_found("Recommendation")
    try:
        access.get_project(db, ctx.user.id, rec.project_id, ProjectRole.EDITOR, action="decide on recommendations")
    except APIError as exc:
        if exc.status_code == 404:
            raise not_found("Recommendation") from exc
        raise
    rec.status, rec.status_reason = body.status, (body.reason or None)
    if body.status in ("accepted", "rejected"):  # also kept as feedback history; accepting is not proof it is right
        feedback_svc.record(db, ctx.user.id, rec, FeedbackType(body.status), body.reason)
    db.commit()
    return _rec(rec, learn.knowledge_used(db, [rec.ai_output_id]))


# --- Component records -------------------------------------------------------------------------


class Spec(BaseModel):
    name: str = Field(min_length=1, max_length=100)
    value: str = Field(min_length=1, max_length=200)
    unit: str | None = Field(default=None, max_length=32)
    source: str = Field(
        min_length=1,
        max_length=300,
        description="Where the value comes from, e.g. 'TI datasheet SLVS123 rev C, table 7.5'",
    )
    verified: bool = False


class Datasheet(BaseModel):
    url: str = Field(min_length=1, max_length=1000)
    title: str | None = Field(default=None, max_length=300)
    revision: str | None = Field(default=None, max_length=64)
    source: str | None = Field(default=None, max_length=300)


class RecordIn(BaseModel):
    manufacturer: str = Field(min_length=1, max_length=200)
    part_number: str = Field(min_length=1, max_length=200)
    description: str | None = Field(default=None, max_length=2000)
    package: str | None = Field(default=None, max_length=200)
    specs: list[Spec] = Field(default_factory=list, max_length=200)
    datasheets: list[Datasheet] = Field(default_factory=list, max_length=20)
    source: str = Field(
        min_length=1, max_length=200, description="Who or what created the record, e.g. 'entered by user'"
    )
    verification: Literal["unverified", "verified"] = "unverified"


class RecordUpdate(BaseModel):
    description: str | None = Field(default=None, max_length=2000)
    package: str | None = Field(default=None, max_length=200)
    specs: list[Spec] | None = Field(default=None, max_length=200)
    datasheets: list[Datasheet] | None = Field(default=None, max_length=20)
    verification: Literal["unverified", "verified"] | None = None


class RecordOut(RecordIn):
    id: uuid.UUID
    project_id: uuid.UUID


class MatchOut(BaseModel):
    reference: str
    value: str | None
    footprint: str
    manufacturer: str | None = Field(description="From the footprint's properties")
    part_number: str | None
    record_id: uuid.UUID | None


def _record(r: ComponentRecord) -> RecordOut:
    return RecordOut(id=r.id, project_id=r.project_id, manufacturer=r.manufacturer, part_number=r.part_number,
                     description=r.description, package=r.package, specs=[Spec(**s) for s in r.specs],
                     datasheets=[Datasheet(**d) for d in r.datasheets], source=r.source,
                     verification=r.verification)  # type: ignore[arg-type]  # fmt: skip


@router.get(
    "/projects/{project_id}/component-records", response_model=list[RecordOut], responses=error_responses(401, 404)
)
def list_records(project_id: uuid.UUID, db: DB, ctx: CurrentAuth, q: str | None = None) -> list[RecordOut]:
    access.get_project(db, ctx.user.id, project_id)
    stmt = select(ComponentRecord).where(ComponentRecord.project_id == project_id)
    if q and q.strip():
        like = f"%{q.strip().replace('%', r'\%').replace('_', r'\_')}%"
        stmt = stmt.where(or_(ComponentRecord.part_number.ilike(like, escape="\\"),
                              ComponentRecord.manufacturer.ilike(like, escape="\\")))  # fmt: skip
    return [_record(r) for r in db.scalars(stmt.order_by(func.lower(ComponentRecord.part_number)).limit(500))]


@router.post("/projects/{project_id}/component-records", response_model=RecordOut, status_code=status.HTTP_201_CREATED,
             responses=error_responses(401, 403, 404, 409, 422))  # fmt: skip
def create_record(project_id: uuid.UUID, body: RecordIn, db: DB, ctx: CurrentAuth) -> RecordOut:
    project, _ = access.get_project(db, ctx.user.id, project_id, ProjectRole.EDITOR, action="manage component records")
    access.ensure_active(project)
    exists = db.scalar(select(ComponentRecord.id).where(
        ComponentRecord.project_id == project.id, ComponentRecord.manufacturer == body.manufacturer.strip(),
        ComponentRecord.part_number == body.part_number.strip()))  # fmt: skip
    if exists is not None:
        raise APIError(409, "record_exists", "This project already has a record for that part.")
    row = ComponentRecord(project_id=project.id, manufacturer=body.manufacturer.strip(), part_number=body.part_number.strip(),
                          description=body.description, package=body.package,
                          specs=[s.model_dump() for s in body.specs], datasheets=[d.model_dump() for d in body.datasheets],
                          source=body.source, verification=body.verification, created_by_id=ctx.user.id)  # fmt: skip
    db.add(row)
    db.commit()
    return _record(row)


def _editable_record(db: DB, ctx: CurrentAuth, record_id: uuid.UUID) -> ComponentRecord:
    row = db.get(ComponentRecord, record_id)
    if row is None:
        raise not_found("Component record")
    try:
        project, _ = access.get_project(
            db, ctx.user.id, row.project_id, ProjectRole.EDITOR, action="manage component records"
        )
    except APIError as exc:
        if exc.status_code == 404:
            raise not_found("Component record") from exc
        raise
    access.ensure_active(project)
    return row


@router.patch("/component-records/{record_id}", response_model=RecordOut, responses=error_responses(401, 403, 404, 422))
def update_record(record_id: uuid.UUID, body: RecordUpdate, db: DB, ctx: CurrentAuth) -> RecordOut:
    row = _editable_record(db, ctx, record_id)
    for field in ("description", "package", "verification"):
        if getattr(body, field) is not None:
            setattr(row, field, getattr(body, field))
    if body.specs is not None:
        row.specs = [s.model_dump() for s in body.specs]
    if body.datasheets is not None:
        row.datasheets = [d.model_dump() for d in body.datasheets]
    db.commit()
    return _record(row)


@router.delete(
    "/component-records/{record_id}", status_code=status.HTTP_204_NO_CONTENT, responses=error_responses(401, 403, 404)
)
def delete_record(record_id: uuid.UUID, db: DB, ctx: CurrentAuth) -> Response:
    db.delete(_editable_record(db, ctx, record_id))
    db.commit()
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.get(
    "/designs/{design_id}/component-matches", response_model=list[MatchOut], responses=error_responses(401, 404, 409)
)
def component_matches(design_id: uuid.UUID, db: DB, ctx: CurrentAuth) -> list[MatchOut]:
    """Each component of the current revision with its part number (from footprint properties) and matching record."""
    design, project, _ = design_svc.get_design(db, ctx.user.id, design_id)
    revision = design_svc.resolve_parsed_revision(db, design, None)
    comps = db.scalars(
        select(PCBComponent).where(PCBComponent.revision_id == revision.id).order_by(PCBComponent.reference)
    ).all()
    return [MatchOut(reference=c.reference, value=c.value, footprint=c.footprint, manufacturer=mfr, part_number=mpn,
                     record_id=r.id if r else None)
            for c, mfr, mpn, r in components.matches(db, project.id, list(comps))]  # fmt: skip
