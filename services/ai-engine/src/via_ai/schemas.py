"""Structured outputs VIA asks models for. Every output is validated against these schemas and then
checked by :mod:`via_ai.verification` before anyone sees it.

Models must cite what they rely on: design objects (component references, net names), finding
ids from the context, and any numbers they use with the context label they came from. Outputs are
always labelled as AI suggestions (``source = ai_suggestion``, unverified) by the API.
"""

from __future__ import annotations

from enum import StrEnum

from pydantic import BaseModel, ConfigDict, Field


class _Out(BaseModel):
    model_config = ConfigDict(extra="forbid")


class Confidence(StrEnum):
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"


class Reference(_Out):
    kind: str = Field(description="component | net | finding | layer | design_rule")
    id: str = Field(
        description="Designator, net name, finding id, layer name or design rule key, exactly as in the context"
    )


class NumberUsed(_Out):
    value: float
    unit: str | None = None
    source: str = Field(description="Where in the context this number comes from, e.g. 'finding <id>: Smallest gap'")


class Explanation(_Out):
    answer: str = Field(description="Direct answer to the question, grounded in the context")
    key_points: list[str] = Field(default_factory=list, max_length=8)
    references: list[Reference] = Field(default_factory=list)
    numbers_used: list[NumberUsed] = Field(default_factory=list)
    uncertainties: list[str] = Field(
        default_factory=list, description="What the context doesn't tell, or assumptions made"
    )
    suggested_validation: list[str] = Field(
        default_factory=list, description="How an engineer could confirm the answer"
    )


class Recommendation(_Out):
    problem: str
    proposed_change: str
    rationale: str = Field(description="Why the change may help")
    expected_benefits: list[str] = Field(default_factory=list)
    trade_offs: list[str] = Field(default_factory=list)
    required_validation: list[str] = Field(default_factory=list)
    evidence_finding_ids: list[str] = Field(default_factory=list, description="Finding ids from the context")
    references: list[Reference] = Field(default_factory=list)
    numbers_used: list[NumberUsed] = Field(default_factory=list)
    confidence: Confidence
    uncertainty: str = Field(description="What could make this recommendation wrong")


class ReviewArea(StrEnum):
    LAYOUT = "layout"
    ROUTING = "routing"
    PLACEMENT = "placement"
    MANUFACTURABILITY = "manufacturability"
    ELECTRICAL = "electrical"
    DESIGN_RULES = "design_rules"


class Hypothesis(_Out):
    statement: str
    rationale: str
    references: list[Reference] = Field(default_factory=list)
    confidence: Confidence
    validation: str = Field(description="How to confirm or refute it")


class ReviewSection(_Out):
    area: ReviewArea
    verified_findings: list[str] = Field(default_factory=list, description="Ids of context findings in this area")
    hypotheses: list[Hypothesis] = Field(
        default_factory=list, description="Engineering hypotheses, clearly not verified"
    )


class DesignReview(_Out):
    summary: str
    sections: list[ReviewSection]
    recommendations: list[Recommendation] = Field(default_factory=list, max_length=20)
