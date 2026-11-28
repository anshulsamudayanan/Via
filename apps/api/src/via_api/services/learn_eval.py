"""Recommendation evaluation (docs/VIA_LEARN.md "Evaluation").

What is measured, and what is deliberately *not* claimed:

* Acceptance and rejection counts are what people decided. They are **not** accuracy.
* Helpful / unhelpful is the latest opinion of each person.
* Grounding rejections are AI answers VIA discarded because they cited things not in the design.
* The only deterministic engineering check is **evidence resolution**: for a recommendation tied to
  analysis findings, did those findings disappear from a later analysis of a newer revision of the same
  design? That shows the problem went away, not that the recommendation caused it or was right.
* False-positive / false-negative rates and per-PCB-type accuracy are not measurable: VIA has no ground
  truth and no board-type classification. Breakdowns use a coarse layer-count and part-count bucket.
"""

from __future__ import annotations

import uuid
from collections import defaultdict
from dataclasses import dataclass
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from via_api.models import (
    AIOutput,
    AnalysisFinding,
    AnalysisRun,
    DesignRevision,
    RecommendationFeedback,
    RecommendationRow,
)
from via_api.models.enums import AnalysisKind, AnalysisStatus, FeedbackType
from via_api.services.feedback import UNCATEGORISED, _uuid

MAX_RECOMMENDATIONS = 5000

NOT_MEASURABLE = [
    {
        "metric": "false positive and false negative rates",
        "reason": "VIA has no ground truth for whether a recommendation was right. The evidence-resolution check "
        "is the only deterministic signal, and it shows a finding went away, not that the advice caused it.",
    },
    {
        "metric": "accuracy by PCB type",
        "reason": "No board-type classification exists. Results are grouped by a coarse layer-count and "
        "part-count bucket, and acceptance there is a human decision, not accuracy.",
    },
]


@dataclass
class Tally:
    recommendations: int = 0
    accepted: int = 0
    rejected: int = 0
    helpful: int = 0
    unhelpful: int = 0
    corrections: int = 0
    incorrect_assumptions: int = 0
    evidence_resolved: int = 0
    evidence_persisting: int = 0
    evidence_not_checkable: int = 0

    def out(self) -> dict[str, Any]:
        decided = self.accepted + self.rejected
        rated = self.helpful + self.unhelpful
        checked = self.evidence_resolved + self.evidence_persisting
        return {
            "recommendations": self.recommendations,
            "accepted": self.accepted,
            "rejected": self.rejected,
            "acceptance_rate": _rate(self.accepted, decided),
            "rejection_rate": _rate(self.rejected, decided),
            "helpful": self.helpful,
            "unhelpful": self.unhelpful,
            "helpful_rate": _rate(self.helpful, rated),
            "corrections": self.corrections,
            "incorrect_assumptions": self.incorrect_assumptions,
            "evidence_resolved": self.evidence_resolved,
            "evidence_persisting": self.evidence_persisting,
            "evidence_not_checkable": self.evidence_not_checkable,
            "evidence_resolution_rate": _rate(self.evidence_resolved, checked),
        }


def _rate(n: int, d: int) -> float | None:
    return round(n / d, 4) if d else None


def board_bucket(object_counts: dict[str, Any] | None) -> str:
    counts = object_counts or {}
    layers, parts = counts.get("copper_layer_count"), counts.get("component_count")
    layer = (
        "layers unknown"
        if not isinstance(layers, int)
        else ("1-2 layers" if layers <= 2 else "3-4 layers" if layers <= 4 else "5+ layers")
    )
    size = (
        "parts unknown"
        if not isinstance(parts, int)
        else ("under 50 parts" if parts < 50 else "50-199 parts" if parts < 200 else "200+ parts")
    )
    return f"{layer}, {size}"


def evidence_status(db: Session, rec: RecommendationRow) -> str:
    """``resolved`` | ``persisting`` | ``not_checkable`` for a recommendation's evidence findings."""
    ids = [i for i in (_uuid(x) for x in rec.evidence_finding_ids) if i]
    if not ids:
        return "not_checkable"
    fingerprints = set(db.scalars(select(AnalysisFinding.fingerprint).where(AnalysisFinding.id.in_(ids))))
    base = db.scalar(select(DesignRevision.revision_number).where(DesignRevision.id == rec.revision_id))
    if not fingerprints or base is None:
        return "not_checkable"
    newer = db.scalars(
        select(DesignRevision.id)
        .where(DesignRevision.design_id == rec.design_id, DesignRevision.revision_number > base)
        .order_by(DesignRevision.revision_number.desc())
    )
    for revision_id in newer:
        run = db.scalar(
            select(AnalysisRun)
            .where(
                AnalysisRun.revision_id == revision_id,
                AnalysisRun.kind == AnalysisKind.PCB_ANALYSIS,
                AnalysisRun.status == AnalysisStatus.SUCCEEDED,
            )
            .order_by(AnalysisRun.created_at.desc())
            .limit(1)
        )
        if run is None:
            continue
        still = db.scalar(
            select(func.count())
            .select_from(AnalysisFinding)
            .where(AnalysisFinding.run_id == run.id, AnalysisFinding.fingerprint.in_(fingerprints))
        )
        return "persisting" if still else "resolved"
    return "not_checkable"


def evaluate(db: Session, project_ids: list[uuid.UUID] | None) -> dict[str, Any]:
    """Metrics for the given projects (``None`` = every project; callers must restrict that to reviewers)."""
    scope: Any = [] if project_ids is None else [RecommendationRow.project_id.in_(project_ids)]
    rows = db.execute(
        select(
            RecommendationRow,
            AIOutput.model,
            AIOutput.prompt_version,
            AnalysisRun.analysis_version,
            DesignRevision.object_counts,
        )
        .join(AIOutput, AIOutput.id == RecommendationRow.ai_output_id)
        .join(AnalysisRun, AnalysisRun.id == AIOutput.analysis_run_id, isouter=True)
        .join(DesignRevision, DesignRevision.id == RecommendationRow.revision_id)
        .where(*scope)
        .order_by(RecommendationRow.created_at.desc())
        .limit(MAX_RECOMMENDATIONS)
    ).all()
    fb_scope: Any = [] if project_ids is None else [RecommendationFeedback.project_id.in_(project_ids)]
    feedback = db.scalars(
        select(RecommendationFeedback).where(*fb_scope).order_by(RecommendationFeedback.created_at)
    ).all()
    latest_opinion: dict[tuple[uuid.UUID, uuid.UUID], FeedbackType] = {}
    extra: dict[uuid.UUID, list[FeedbackType]] = defaultdict(list)
    for f in feedback:
        if f.feedback_type in (FeedbackType.HELPFUL, FeedbackType.UNHELPFUL):
            latest_opinion[(f.user_id, f.recommendation_id)] = f.feedback_type
        elif f.feedback_type in (FeedbackType.CORRECTION, FeedbackType.INCORRECT_ASSUMPTION):
            extra[f.recommendation_id].append(f.feedback_type)
    opinions: dict[uuid.UUID, list[FeedbackType]] = defaultdict(list)
    for (_, rec_id), kind in latest_opinion.items():
        opinions[rec_id].append(kind)

    total = Tally()
    by_category: dict[str, Tally] = defaultdict(Tally)
    by_version: dict[tuple[str, str, str | None], Tally] = defaultdict(Tally)
    by_bucket: dict[str, Tally] = defaultdict(Tally)
    for rec, model, prompt_version, engine_version, counts in rows:
        status = evidence_status(db, rec)
        category = _category(db, rec)
        for tally in (
            total,
            by_category[category],
            by_version[(model, prompt_version, engine_version)],
            by_bucket[board_bucket(counts)],
        ):
            tally.recommendations += 1
            tally.accepted += rec.status == "accepted"
            tally.rejected += rec.status == "rejected"
            tally.helpful += opinions[rec.id].count(FeedbackType.HELPFUL)
            tally.unhelpful += opinions[rec.id].count(FeedbackType.UNHELPFUL)
            tally.corrections += extra[rec.id].count(FeedbackType.CORRECTION)
            tally.incorrect_assumptions += extra[rec.id].count(FeedbackType.INCORRECT_ASSUMPTION)
            tally.evidence_resolved += status == "resolved"
            tally.evidence_persisting += status == "persisting"
            tally.evidence_not_checkable += status == "not_checkable"

    out_scope: Any = [] if project_ids is None else [AIOutput.project_id.in_(project_ids)]
    grounding_rows = db.execute(
        select(AIOutput.model, AIOutput.prompt_version, AIOutput.accepted, func.count())
        .where(AIOutput.kind == "design_review", *out_scope)
        .group_by(AIOutput.model, AIOutput.prompt_version, AIOutput.accepted)
    ).all()
    grounding: dict[tuple[str, str], list[int]] = defaultdict(lambda: [0, 0])
    for model, prompt_version, accepted, n in grounding_rows:
        grounding[(model, prompt_version)][0 if accepted else 1] += n
    g_ok, g_bad = sum(v[0] for v in grounding.values()), sum(v[1] for v in grounding.values())

    versions = []
    for (model, prompt_version, engine_version), tally in sorted(
        by_version.items(), key=lambda kv: -kv[1].recommendations
    ):
        ok, bad = grounding.get((model, prompt_version), [0, 0])
        versions.append(
            {"model": model, "prompt_version": prompt_version, "engine_version": engine_version, **tally.out(),
             "reviews": ok + bad, "grounding_rejected": bad, "grounding_rejection_rate": _rate(bad, ok + bad)}
        )  # fmt: skip
    return {
        "scope": "global" if project_ids is None else "projects",
        "projects": None if project_ids is None else len(project_ids),
        "capped": len(rows) >= MAX_RECOMMENDATIONS,
        "summary": total.out(),
        "grounding": {"reviews": g_ok + g_bad, "rejected": g_bad, "rejection_rate": _rate(g_bad, g_ok + g_bad)},
        "by_category": [{"category": k, **v.out()} for k, v in sorted(by_category.items())],
        "by_version": versions,
        "by_board_bucket": [{"bucket": k, **v.out()} for k, v in sorted(by_bucket.items())],
        "not_measurable": NOT_MEASURABLE,
        "notes": [
            "Acceptance and rejection are people's decisions, not measures of engineering accuracy.",
            "Evidence resolution means the findings behind a recommendation no longer appear in a later analysis of a "
            "newer revision. It does not show the recommendation caused that.",
        ],
    }


def _category(db: Session, rec: RecommendationRow) -> str:
    from via_api.services.feedback import recommendation_category

    return recommendation_category(db, rec) or UNCATEGORISED
