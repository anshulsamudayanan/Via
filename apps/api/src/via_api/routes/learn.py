"""/api/v1/learn and recommendation feedback: VIA Learn (docs/VIA_LEARN.md).

Feedback is private to the project (project roles apply). The knowledge library is the separate,
de-identified store: anything in it was contributed on purpose and approved by a reviewer.
"""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Annotated, Any

from fastapi import APIRouter, Query, Response, status
from pydantic import BaseModel, Field

from via_api.deps import DB, Client, CurrentAuth, Limiter
from via_api.errors import APIError, error_responses
from via_api.models import LearnEntry, LearnEntryVersion, Project, RecommendationFeedback
from via_api.models.enums import (
    ConsentScope,
    FeedbackType,
    LearnCategory,
    LearnStatus,
    LearnVerification,
    ProjectRole,
)
from via_api.ratelimit import FEEDBACK_PER_USER, LEARN_READS_PER_USER, LEARN_WRITES_PER_USER
from via_api.schemas.common import Page
from via_api.services import access, consent, learn, learn_eval
from via_api.services import feedback as feedback_svc

router = APIRouter(tags=["learn"])

LIMIT = Query(20, ge=1, le=100)
OFFSET = Query(0, ge=0)


# --- schemas ---------------------------------------------------------------------------------------------------


class FeedbackIn(BaseModel):
    feedback_type: FeedbackType
    explanation: str | None = Field(default=None, max_length=4000)


class FeedbackOut(BaseModel):
    id: uuid.UUID
    recommendation_id: uuid.UUID
    project_id: uuid.UUID
    design_id: uuid.UUID
    analysis_run_id: uuid.UUID | None
    category: str
    feedback_type: FeedbackType
    explanation: str | None
    model: str
    prompt_version: str
    engine_version: str | None
    by: str
    mine: bool
    created_at: datetime


class EntryOut(BaseModel):
    """What anyone may see of an entry. Never the contributor's identity or anything about a project."""

    id: uuid.UUID
    category: LearnCategory
    title: str
    description: str
    technical_metadata: dict[str, Any]
    source: str
    provenance: dict[str, Any]
    origin: str
    status: LearnStatus
    verification_status: LearnVerification
    verification_basis: str | None
    version: int
    mine: bool
    score: float | None = None
    #: Only for the contributor and reviewers.
    permissions: dict[str, Any] | None = None
    review_note: str | None = None
    submitted_at: datetime | None = None
    reviewed_at: datetime | None = None
    withdrawn_at: datetime | None = None
    created_at: datetime
    updated_at: datetime


class VersionOut(BaseModel):
    version: int
    change: str
    title: str
    description: str
    verification_status: LearnVerification
    created_at: datetime


class ContributionIn(BaseModel):
    category: LearnCategory
    title: str = Field(min_length=5, max_length=200)
    description: str = Field(min_length=20, max_length=6000)
    source: str = Field(min_length=3, max_length=1000, description="Where the knowledge comes from")
    technical_metadata: dict[str, Any] = Field(default_factory=dict)
    #: The contributor confirms the text is theirs to share and contains nothing from a private design.
    confirm_rights: bool


class DeriveIn(BaseModel):
    category: LearnCategory | None = None


class PermissionsIn(BaseModel):
    library_visible: bool | None = None
    ai_retrieval: bool | None = None


class ReviewIn(BaseModel):
    decision: str = Field(pattern="^(approve|reject)$")
    note: str | None = Field(default=None, max_length=2000)
    verification_status: LearnVerification = LearnVerification.UNVERIFIED
    verification_basis: str | None = Field(default=None, max_length=2000)


class VerificationIn(BaseModel):
    verification_status: LearnVerification
    verification_basis: str | None = Field(default=None, max_length=2000)


class LearnConsentOut(BaseModel):
    project_id: uuid.UUID
    granted: bool
    policy_version: str
    granted_at: datetime | None = None
    withdrawn_entries: int = 0


class Meta(BaseModel):
    categories: list[str]
    verification_levels: list[dict[str, str]]
    is_reviewer: bool
    policy_version: str
    retrieval: dict[str, Any]


def _entry(entry: LearnEntry, user_id: uuid.UUID, is_reviewer: bool, score: float | None = None) -> EntryOut:
    mine = entry.contributor_id == user_id
    private = mine or is_reviewer
    return EntryOut(
        id=entry.id,
        category=entry.category,
        title=entry.title,
        description=entry.description,
        technical_metadata=entry.technical_metadata,
        source=entry.source,
        provenance=entry.provenance,
        origin=entry.origin.value,
        status=entry.status,
        verification_status=entry.verification_status,
        verification_basis=entry.verification_basis,
        version=entry.version,
        mine=mine,
        score=score,
        permissions=entry.permissions if private else None,
        review_note=entry.review_note if private else None,
        submitted_at=entry.submitted_at if private else None,
        reviewed_at=entry.reviewed_at,
        withdrawn_at=entry.withdrawn_at,
        created_at=entry.created_at,
        updated_at=entry.updated_at,
    )


def _feedback(row: RecommendationFeedback, name: str, user_id: uuid.UUID) -> FeedbackOut:
    return FeedbackOut(
        id=row.id,
        recommendation_id=row.recommendation_id,
        project_id=row.project_id,
        design_id=row.design_id,
        analysis_run_id=row.analysis_run_id,
        category=row.category,
        feedback_type=row.feedback_type,
        explanation=row.explanation,
        model=row.model,
        prompt_version=row.prompt_version,
        engine_version=row.engine_version,
        by=name,
        mine=row.user_id == user_id,
        created_at=row.created_at,
    )


# --- feedback (private to the project) -------------------------------------------------------------------------


@router.post(
    "/recommendations/{recommendation_id}/feedback",
    response_model=FeedbackOut,
    status_code=201,
    responses=error_responses(401, 403, 404, 422, 429),
)
def give_feedback(
    recommendation_id: uuid.UUID, body: FeedbackIn, db: DB, ctx: CurrentAuth, client: Client, limiter: Limiter
) -> FeedbackOut:
    """Helpful, unhelpful, a correction, an incorrect assumption or a comment (editor). Accept and reject keep
    using `PATCH /recommendations/{id}`, which also lands in this history."""
    if body.feedback_type in (FeedbackType.ACCEPTED, FeedbackType.REJECTED):
        raise APIError(422, "use_decision", "Accept or reject through the recommendation's decision.")
    rec_row = feedback_svc.get_recommendation(db, ctx, recommendation_id, ProjectRole.EDITOR)
    limiter.hit(FEEDBACK_PER_USER, str(ctx.user.id))
    row = feedback_svc.submit(db, ctx, rec_row.id, body.feedback_type, body.explanation, client)
    db.commit()
    return _feedback(row, ctx.user.display_name, ctx.user.id)


@router.get("/learn/feedback", response_model=Page[FeedbackOut], responses=error_responses(401, 404))
def feedback_history(
    db: DB,
    ctx: CurrentAuth,
    project_id: uuid.UUID | None = None,
    recommendation_id: uuid.UUID | None = None,
    mine: bool = False,
    limit: int = LIMIT,
    offset: int = OFFSET,
) -> Page[FeedbackOut]:
    rows, total = feedback_svc.history(
        db, ctx, project_id=project_id, recommendation_id=recommendation_id, mine=mine, limit=limit, offset=offset
    )
    return Page(items=[_feedback(r, n, ctx.user.id) for r, n in rows], total=total, limit=limit, offset=offset)


# --- library ---------------------------------------------------------------------------------------------------


@router.get("/learn/meta", response_model=Meta, responses=error_responses(401))
def learn_meta(ctx: CurrentAuth) -> Meta:
    return Meta(
        categories=[c.value for c in LearnCategory],
        verification_levels=[
            {
                "id": "unverified",
                "label": "Unverified",
                "meaning": "Approved for the library; nobody has confirmed it.",
            },
            {
                "id": "reviewed",
                "label": "Reviewed",
                "meaning": "A reviewer read it and found it plausible, with a stated basis.",
            },
            {
                "id": "verified",
                "label": "Verified",
                "meaning": "A reviewer checked it against a source or a deterministic check.",
            },
        ],
        is_reviewer=ctx.user.learn_reviewer,
        policy_version=consent.POLICY_VERSION,
        retrieval={
            "method": "keyword",
            "semantic": False,
            "note": "Matches words in titles and descriptions, ranked by relevance and verification. "
            "It does not understand meaning.",
        },
    )


@router.get("/learn/entries", response_model=Page[EntryOut], responses=error_responses(401, 429))
def search_entries(
    db: DB,
    ctx: CurrentAuth,
    limiter: Limiter,
    q: Annotated[str | None, Query(max_length=300)] = None,
    category: LearnCategory | None = None,
    verification: LearnVerification | None = None,
    limit: int = LIMIT,
    offset: int = OFFSET,
) -> Page[EntryOut]:
    """Search approved knowledge (everyone signed in). Never returns drafts, rejected or withdrawn entries."""
    limiter.hit(LEARN_READS_PER_USER, str(ctx.user.id))
    hits, total = learn.search(db, q, category=category, verification=verification, limit=limit, offset=offset)
    return Page(
        items=[_entry(h.entry, ctx.user.id, ctx.user.learn_reviewer, h.score) for h in hits],
        total=total,
        limit=limit,
        offset=offset,
    )


@router.get("/learn/entries/{entry_id}", response_model=EntryOut, responses=error_responses(401, 404))
def get_entry(entry_id: uuid.UUID, db: DB, ctx: CurrentAuth) -> EntryOut:
    return _entry(learn.get_entry(db, ctx, entry_id), ctx.user.id, ctx.user.learn_reviewer)


@router.get("/learn/entries/{entry_id}/versions", response_model=list[VersionOut], responses=error_responses(401, 404))
def entry_versions(entry_id: uuid.UUID, db: DB, ctx: CurrentAuth) -> list[LearnEntryVersion]:
    return learn.versions(db, ctx, entry_id)


# --- contributions ---------------------------------------------------------------------------------------------


@router.post("/learn/contributions", response_model=EntryOut, status_code=201, responses=error_responses(401, 422, 429))
def create_contribution(body: ContributionIn, db: DB, ctx: CurrentAuth, client: Client, limiter: Limiter) -> EntryOut:
    """A draft written by you. It stays a draft, visible only to you, until you submit it for review."""
    limiter.hit(LEARN_WRITES_PER_USER, str(ctx.user.id))
    if not body.confirm_rights:
        raise APIError(
            422, "rights_required", "Confirm that this is yours to share and contains nothing from a private design."
        )
    entry = learn.create_free_text(
        db,
        ctx,
        category=body.category,
        title=body.title,
        description=body.description,
        source=body.source,
        technical_metadata=body.technical_metadata,
        client=client,
    )
    db.commit()
    return _entry(entry, ctx.user.id, ctx.user.learn_reviewer)


@router.post(
    "/recommendations/{recommendation_id}/contribute",
    response_model=EntryOut,
    status_code=201,
    responses=error_responses(401, 403, 404, 409, 429),
)
def contribute_recommendation(
    recommendation_id: uuid.UUID, body: DeriveIn, db: DB, ctx: CurrentAuth, client: Client, limiter: Limiter
) -> EntryOut:
    """Draft a contribution from one of your project's recommendations, with the design's part references, net
    names and names removed. Needs the project owner's VIA Learn consent. Review the draft, then submit it."""
    limiter.hit(LEARN_WRITES_PER_USER, str(ctx.user.id))
    entry = learn.create_from_recommendation(db, ctx, recommendation_id, body.category, client)
    db.commit()
    return _entry(entry, ctx.user.id, ctx.user.learn_reviewer)


@router.get("/learn/contributions", response_model=Page[EntryOut], responses=error_responses(401))
def my_contributions(
    db: DB,
    ctx: CurrentAuth,
    status_: Annotated[LearnStatus | None, Query(alias="status")] = None,
    limit: int = LIMIT,
    offset: int = OFFSET,
) -> Page[EntryOut]:
    rows, total = learn.list_mine(db, ctx, status_, limit, offset)
    return Page(
        items=[_entry(e, ctx.user.id, ctx.user.learn_reviewer) for e in rows], total=total, limit=limit, offset=offset
    )


@router.post(
    "/learn/contributions/{entry_id}/submit", response_model=EntryOut, responses=error_responses(401, 403, 404, 409)
)
def submit_contribution(entry_id: uuid.UUID, db: DB, ctx: CurrentAuth, client: Client, limiter: Limiter) -> EntryOut:
    limiter.hit(LEARN_WRITES_PER_USER, str(ctx.user.id))
    entry = learn.submit(db, ctx, entry_id, client)
    db.commit()
    return _entry(entry, ctx.user.id, ctx.user.learn_reviewer)


@router.delete(
    "/learn/contributions/{entry_id}", status_code=status.HTTP_204_NO_CONTENT, responses=error_responses(401, 404, 409)
)
def delete_draft(entry_id: uuid.UUID, db: DB, ctx: CurrentAuth) -> Response:
    learn.delete_draft(db, ctx, entry_id)
    db.commit()
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.post("/learn/contributions/{entry_id}/withdraw", response_model=EntryOut, responses=error_responses(401, 404))
def withdraw_contribution(entry_id: uuid.UUID, db: DB, ctx: CurrentAuth, client: Client) -> EntryOut:
    """Withdraw your contribution (or, for a reviewer, take an entry down): it leaves search and the AI at once
    and its content is erased. The id, ownership and provenance stay for audit."""
    entry = learn.withdraw(db, ctx, entry_id, client)
    db.commit()
    return _entry(entry, ctx.user.id, ctx.user.learn_reviewer)


@router.put(
    "/learn/contributions/{entry_id}/permissions", response_model=EntryOut, responses=error_responses(401, 404, 409)
)
def contribution_permissions(
    entry_id: uuid.UUID, body: PermissionsIn, db: DB, ctx: CurrentAuth, client: Client
) -> EntryOut:
    """Choose whether an entry shows in the library and whether the AI may retrieve it."""
    entry = learn.update_permissions(
        db, ctx, entry_id, library_visible=body.library_visible, ai_retrieval=body.ai_retrieval, client=client
    )
    db.commit()
    return _entry(entry, ctx.user.id, ctx.user.learn_reviewer)


# --- review (reviewers only) -----------------------------------------------------------------------------------


@router.get("/learn/review", response_model=Page[EntryOut], responses=error_responses(401, 403))
def review_queue(db: DB, ctx: CurrentAuth, limit: int = LIMIT, offset: int = OFFSET) -> Page[EntryOut]:
    rows, total = learn.review_queue(db, ctx, limit, offset)
    return Page(items=[_entry(e, ctx.user.id, True) for e in rows], total=total, limit=limit, offset=offset)


@router.post(
    "/learn/contributions/{entry_id}/review",
    response_model=EntryOut,
    responses=error_responses(401, 403, 404, 409, 422),
)
def review_contribution(entry_id: uuid.UUID, body: ReviewIn, db: DB, ctx: CurrentAuth, client: Client) -> EntryOut:
    """Approve (optionally marking it reviewed or verified, with the basis) or reject (with a reason). You can't
    review your own contribution."""
    entry = learn.review(
        db,
        ctx,
        entry_id,
        approve=body.decision == "approve",
        note=body.note,
        verification=body.verification_status,
        basis=body.verification_basis,
        client=client,
    )
    db.commit()
    return _entry(entry, ctx.user.id, True)


@router.put(
    "/learn/entries/{entry_id}/verification",
    response_model=EntryOut,
    responses=error_responses(401, 403, 404, 409, 422),
)
def set_verification(entry_id: uuid.UUID, body: VerificationIn, db: DB, ctx: CurrentAuth, client: Client) -> EntryOut:
    entry = learn.set_verification(
        db, ctx, entry_id, verification=body.verification_status, basis=body.verification_basis, client=client
    )
    db.commit()
    return _entry(entry, ctx.user.id, True)


# --- project consent -------------------------------------------------------------------------------------------


def _consent_out(db: DB, project_id: uuid.UUID, withdrawn: int = 0) -> LearnConsentOut:
    row = consent.active_consent(db, project_id, ConsentScope.VIA_LEARN_CONTRIBUTION)
    return LearnConsentOut(
        project_id=project_id,
        granted=row is not None,
        policy_version=consent.POLICY_VERSION,
        granted_at=row.granted_at if row else None,
        withdrawn_entries=withdrawn,
    )


@router.get("/projects/{project_id}/learn-consent", response_model=LearnConsentOut, responses=error_responses(401, 404))
def get_learn_consent(project_id: uuid.UUID, db: DB, ctx: CurrentAuth) -> LearnConsentOut:
    access.get_project(db, ctx.user.id, project_id)
    return _consent_out(db, project_id)


@router.put(
    "/projects/{project_id}/learn-consent", response_model=LearnConsentOut, responses=error_responses(401, 403, 404)
)
def grant_learn_consent(project_id: uuid.UUID, db: DB, ctx: CurrentAuth, client: Client) -> LearnConsentOut:
    """Owner only. Allows *drafting* contributions from this project; each one still needs your review and
    confirmation. Nothing is contributed automatically."""
    learn.grant_learn_consent(db, ctx, project_id, client)
    db.commit()
    return _consent_out(db, project_id)


@router.delete(
    "/projects/{project_id}/learn-consent", response_model=LearnConsentOut, responses=error_responses(401, 403, 404)
)
def revoke_learn_consent(
    project_id: uuid.UUID, db: DB, ctx: CurrentAuth, client: Client, withdraw_existing: bool = True
) -> LearnConsentOut:
    """Owner only. Stops future contributions and, unless `withdraw_existing=false`, withdraws what this
    project already contributed."""
    n = learn.revoke_learn_consent(db, ctx, project_id, client, withdraw_existing=withdraw_existing)
    db.commit()
    return _consent_out(db, project_id, n)


# --- evaluation ------------------------------------------------------------------------------------------------


@router.get("/learn/evaluation", responses=error_responses(401, 404))
def evaluation(db: DB, ctx: CurrentAuth, project_id: uuid.UUID | None = None) -> dict[str, Any]:
    """Recommendation quality for one project (any member) or for all projects you can access."""
    from sqlalchemy import select

    if project_id is not None:
        access.get_project(db, ctx.user.id, project_id)
        ids = [project_id]
    else:
        ids = list(db.scalars(select(Project.id).where(access.accessible_projects_clause(ctx.user.id))))
    return learn_eval.evaluate(db, ids)


@router.get("/learn/evaluation/global", responses=error_responses(401, 403))
def global_evaluation(db: DB, ctx: CurrentAuth) -> dict[str, Any]:
    """Counts and rates across every project, grouped by version, category and board size. Reviewers only; no
    content from any project."""
    learn.require_reviewer(ctx)
    return learn_eval.evaluate(db, None)
