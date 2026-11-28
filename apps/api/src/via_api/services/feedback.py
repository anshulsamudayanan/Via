"""Feedback on AI recommendations (private to the project; docs/VIA_LEARN.md).

Feedback rows are append-only: a later opinion is a new row. Accepting a recommendation is recorded as
feedback but is *not* treated as evidence it is right (see ``learn_eval`` for what is measured instead).
"""

from __future__ import annotations

import uuid

from sqlalchemy import select
from sqlalchemy.orm import Session

from via_api.errors import APIError, not_found
from via_api.models import (
    AIOutput,
    AnalysisFinding,
    AnalysisRun,
    Project,
    RecommendationFeedback,
    RecommendationRow,
    User,
)
from via_api.models.enums import FeedbackType, ProjectRole
from via_api.services import access, activity
from via_api.services.activity import ClientInfo
from via_api.services.auth import AuthContext

FEEDBACK_SUBMITTED = "feedback.submitted"
#: These say something specific, so they need the user's words.
NEEDS_EXPLANATION = {
    FeedbackType.REJECTED,
    FeedbackType.CORRECTION,
    FeedbackType.INCORRECT_ASSUMPTION,
    FeedbackType.COMMENT,
}
UNCATEGORISED = "uncategorised"


def _uuid(value: str) -> uuid.UUID | None:
    try:
        return uuid.UUID(str(value))
    except ValueError:
        return None


def recommendation_category(db: Session, rec: RecommendationRow) -> str:
    """Finding category of the recommendation's first evidence finding that still exists."""
    for raw in rec.evidence_finding_ids:
        fid = _uuid(raw)
        if fid is None:
            continue
        category = db.scalar(select(AnalysisFinding.category).where(AnalysisFinding.id == fid))
        if category is not None:
            return str(category.value)
    return UNCATEGORISED


def record(
    db: Session,
    user_id: uuid.UUID,
    rec: RecommendationRow,
    feedback_type: FeedbackType,
    explanation: str | None,
    client: ClientInfo | None = None,
) -> RecommendationFeedback:
    """Store one feedback row with the versions in force when the recommendation was made. No access check:
    callers have already checked the project role."""
    ai = db.get(AIOutput, rec.ai_output_id)
    run = db.get(AnalysisRun, ai.analysis_run_id) if ai is not None and ai.analysis_run_id is not None else None
    row = RecommendationFeedback(
        recommendation_id=rec.id,
        project_id=rec.project_id,
        design_id=rec.design_id,
        analysis_run_id=ai.analysis_run_id if ai else None,
        user_id=user_id,
        category=recommendation_category(db, rec),
        feedback_type=feedback_type,
        explanation=(explanation or "").strip() or None,
        model=ai.model if ai else "unknown",
        prompt_version=ai.prompt_version if ai else "unknown",
        engine_version=run.analysis_version if run else None,
    )
    db.add(row)
    db.flush()
    activity.record(
        db,
        FEEDBACK_SUBMITTED,
        actor_id=user_id,
        client=client,
        project_id=rec.project_id,
        target_type="recommendation",
        target_id=rec.id,
        details={"type": feedback_type.value},
    )
    return row


def get_recommendation(
    db: Session, ctx: AuthContext, recommendation_id: uuid.UUID, minimum: ProjectRole
) -> RecommendationRow:
    rec = db.get(RecommendationRow, recommendation_id)
    if rec is None:
        raise not_found("Recommendation")
    try:
        project, _ = access.get_project(db, ctx.user.id, rec.project_id, minimum, action="give feedback")
    except APIError as exc:
        if exc.status_code == 404:
            raise not_found("Recommendation") from exc
        raise
    access.ensure_active(project) if minimum != ProjectRole.VIEWER else None
    return rec


def submit(
    db: Session,
    ctx: AuthContext,
    recommendation_id: uuid.UUID,
    feedback_type: FeedbackType,
    explanation: str | None,
    client: ClientInfo,
) -> RecommendationFeedback:
    rec = get_recommendation(db, ctx, recommendation_id, ProjectRole.EDITOR)
    if feedback_type in NEEDS_EXPLANATION and not (explanation or "").strip():
        raise APIError(422, "explanation_required", "Say what was wrong, or what you'd change.")
    return record(db, ctx.user.id, rec, feedback_type, explanation, client)


def history(
    db: Session,
    ctx: AuthContext,
    *,
    project_id: uuid.UUID | None,
    recommendation_id: uuid.UUID | None,
    mine: bool,
    limit: int,
    offset: int,
) -> tuple[list[tuple[RecommendationFeedback, str]], int]:
    """Feedback on projects the caller can see (404 for a project they can't), newest first."""
    from sqlalchemy import func

    if project_id is not None:
        access.get_project(db, ctx.user.id, project_id)
    if recommendation_id is not None:
        get_recommendation(db, ctx, recommendation_id, ProjectRole.VIEWER)
    visible = select(Project.id).where(access.accessible_projects_clause(ctx.user.id))
    stmt = select(RecommendationFeedback, User.display_name).join(User, User.id == RecommendationFeedback.user_id)
    stmt = stmt.where(RecommendationFeedback.project_id.in_(visible))
    if project_id is not None:
        stmt = stmt.where(RecommendationFeedback.project_id == project_id)
    if recommendation_id is not None:
        stmt = stmt.where(RecommendationFeedback.recommendation_id == recommendation_id)
    if mine:
        stmt = stmt.where(RecommendationFeedback.user_id == ctx.user.id)
    total = db.scalar(select(func.count()).select_from(stmt.subquery())) or 0
    rows = db.execute(stmt.order_by(RecommendationFeedback.created_at.desc()).limit(limit).offset(offset)).all()
    return [(row, name) for row, name in rows], total
