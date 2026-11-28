"""Candidates: a proposed change set with its measured effect and validation result."""

from __future__ import annotations

from enum import StrEnum
from typing import Any

from pydantic import BaseModel, ConfigDict, Field

from via_opt.changes import Change
from via_opt.rules import ConstraintResult


class CandidateStatus(StrEnum):
    PROPOSED = "proposed"
    AWAITING_VALIDATION = "awaiting_validation"
    VALIDATED = "validated"
    REJECTED = "rejected"
    ACCEPTED = "accepted"


class ValidationStatus(StrEnum):
    PASSED = "passed"  # VIA re-checked the modified design: no new problems
    FAILED = "failed"  # new problems or constraint violations
    REQUIRES_REROUTING = "requires_rerouting"  # moved routed parts: must be re-routed before it can be validated
    MANUAL = "manual"  # can't be applied automatically (e.g. layer count)
    UNVERIFIED = "unverified"  # a hard requirement the engineer declared can't be checked by VIA: needs review


class Validation(BaseModel):
    model_config = ConfigDict(extra="forbid")

    status: ValidationStatus
    checks_run: list[str] = Field(default_factory=list)
    new_problems: list[str] = Field(default_factory=list)
    resolved_problems: int = 0
    constraint_violations: list[str] = Field(default_factory=list)
    constraints: list[ConstraintResult] = Field(default_factory=list, description="Every constraint and its result")
    notes: list[str] = Field(default_factory=list)


class Score(BaseModel):
    """A weighted preference over the requested objectives (lower is better). Display order only: it never
    changes validation or the Pareto front. See docs/OPTIMIZATION_CONSTRAINTS.md."""

    model_config = ConfigDict(extra="forbid")

    value: float | None
    rank: int | None = None
    partial: bool = False
    excluded: list[str] = Field(default_factory=list, description="Metrics left out, and why")
    weights: dict[str, float] = Field(default_factory=dict)


class Candidate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    key: str = Field(description="Stable within a run, e.g. 'outline_fit'")
    algorithm: str
    algorithm_version: str
    objectives: list[str]
    title: str
    summary: str
    changes: list[Change]
    metrics_before: dict[str, float | None]
    metrics_after: dict[str, float | None]
    expected_benefits: list[str] = Field(default_factory=list)
    trade_offs: list[str] = Field(default_factory=list)
    validation: Validation
    status: CandidateStatus
    details: dict[str, Any] = Field(default_factory=dict)
    warnings: list[str] = Field(default_factory=list)
    limitations: list[str] = Field(default_factory=list)
    execution: dict[str, Any] = Field(
        default_factory=dict, description="Seed, parameters, timing; never used for equality"
    )
    score: Score | None = None
    candidate_hash: str = Field(default="", description="sha256 of the algorithm, version and canonical changes")
