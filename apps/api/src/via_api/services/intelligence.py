# ruff: noqa: E501
"""AI features in the API: grounded explanations and design reviews, with audit and verification.

Flow: authorization → consent (external providers) → bounded context from database rows only →
structured model output → verification against that context → stored as an ``ai_outputs`` row
(accepted or rejected). Rejected outputs are never returned as answers.
"""

from __future__ import annotations

import logging
import uuid
from typing import Any

from sqlalchemy.orm import Session

from via_ai import AIError, AIProvider, AIRefusedError, AIResult, ContextPurpose, explain, review
from via_api.ai.context import DatabaseContextProvider
from via_api.errors import APIError
from via_api.models import AIOutput, DesignRevision, RecommendationRow
from via_api.services import activity
from via_api.services.activity import ClientInfo
from via_api.services.auth import AuthContext

AI_EXPLAINED = "ai.explained"
AI_REVIEWED = "ai.reviewed"


def _require(provider: AIProvider) -> None:
    if not provider.capabilities.structured_output:
        raise APIError(503, "ai_disabled", "AI features are turned off on this server.")


logger = logging.getLogger("via_api.ai")


def _store(db: Session, ctx: AuthContext, provider: AIProvider, kind: str, context: Any, result: AIResult[Any],
           question: str | None, focus: dict[str, str] | None) -> AIOutput:  # fmt: skip
    revision = db.get(DesignRevision, context.revision_id)
    assert revision is not None
    row = AIOutput(
        project_id=context.project_id, design_id=context.design_id, revision_id=context.revision_id,
        analysis_run_id=context.analysis_run_id, kind=kind, question=question, focus=focus,
        provider=provider.name, model=result.model, prompt_version=result.prompt_version,
        context_sha256=result.context_sha256, output=result.value.model_dump(mode="json"),
        accepted=result.accepted, verification=result.report.model_dump(mode="json"),
        input_tokens=result.usage.input_tokens, output_tokens=result.usage.output_tokens,
        created_by_id=ctx.user.id,
    )  # fmt: skip
    db.add(row)
    db.flush()
    return row


def _call(fn: Any, *args: Any) -> Any:
    try:
        return fn(*args)
    except AIRefusedError as exc:
        raise APIError(422, "ai_refused", "The AI model declined to answer this request.") from exc
    except AIError as exc:
        raise APIError(503, "ai_unavailable", str(exc) or "The AI provider is unavailable.") from exc
    except Exception as exc:  # a provider or parsing bug must not surface as an opaque HTTP 500
        logger.exception("AI call failed unexpectedly")
        raise APIError(
            503, "ai_unavailable", f"The AI request failed unexpectedly ({type(exc).__name__}). See the API log."
        ) from exc


def _reject_if_needed(db: Session, row: AIOutput, result: AIResult[Any]) -> None:
    if not result.accepted:
        db.commit()  # keep the rejected output for audit
        raise APIError(
            502,
            "ai_output_rejected",
            "The AI answer referred to things that aren't in this design, so VIA discarded it. Try rephrasing.",
            {"problems": result.report.problems[:20], "ai_output_id": str(row.id)},
        )


def explain_design(db: Session, ctx: AuthContext, provider: AIProvider, design_id: uuid.UUID, question: str,
                   focus: tuple[str, str] | None, run_id: uuid.UUID | None, client: ClientInfo) -> AIOutput:  # fmt: skip
    _require(provider)
    context = DatabaseContextProvider(db).build(
        user_id=ctx.user.id, design_id=design_id, purpose=ContextPurpose.EXPLAIN,
        external=provider.capabilities.external, focus=focus, run_id=run_id,
    )  # fmt: skip
    result = _call(explain, provider, context, question)
    row = _store(db, ctx, provider, "explanation", context, result, question,
                 {"kind": focus[0], "id": focus[1]} if focus else None)  # fmt: skip
    _reject_if_needed(db, row, result)
    activity.record(db, AI_EXPLAINED, actor_id=ctx.user.id, client=client, project_id=context.project_id,
                    target_type="ai_output", target_id=row.id, details={"focus": focus[0] if focus else None})  # fmt: skip
    return row


def review_design(db: Session, ctx: AuthContext, provider: AIProvider, design_id: uuid.UUID,
                  run_id: uuid.UUID | None, client: ClientInfo) -> tuple[AIOutput, list[RecommendationRow]]:  # fmt: skip
    _require(provider)
    context = DatabaseContextProvider(db).build(
        user_id=ctx.user.id, design_id=design_id, purpose=ContextPurpose.DESIGN_REVIEW,
        external=provider.capabilities.external, run_id=run_id,
    )  # fmt: skip
    result = _call(review, provider, context)
    row = _store(db, ctx, provider, "design_review", context, result, None, None)
    _reject_if_needed(db, row, result)
    recs = []
    for r in result.value.recommendations:
        rec = RecommendationRow(
            ai_output_id=row.id, project_id=context.project_id, design_id=context.design_id,
            revision_id=context.revision_id, problem=r.problem, proposed_change=r.proposed_change,
            rationale=r.rationale, evidence_finding_ids=r.evidence_finding_ids, confidence=r.confidence.value,
            details={"expected_benefits": r.expected_benefits, "trade_offs": r.trade_offs,
                     "required_validation": r.required_validation, "uncertainty": r.uncertainty,
                     "references": [x.model_dump() for x in r.references],
                     "numbers_used": [x.model_dump() for x in r.numbers_used]},
        )  # fmt: skip
        db.add(rec)
        recs.append(rec)
    activity.record(db, AI_REVIEWED, actor_id=ctx.user.id, client=client, project_id=context.project_id,
                    target_type="ai_output", target_id=row.id, details={"recommendations": len(recs)})  # fmt: skip
    db.flush()
    return row, recs
