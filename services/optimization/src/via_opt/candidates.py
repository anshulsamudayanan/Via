"""Candidates: a proposed change set with its measured effect and validation result."""

from __future__ import annotations

from enum import StrEnum
from typing import Any

from pydantic import BaseModel, ConfigDict, Field

from via_opt.changes import Change


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


class Validation(BaseModel):
    model_config = ConfigDict(extra="forbid")

    status: ValidationStatus
    checks_run: list[str] = Field(default_factory=list)
    new_problems: list[str] = Field(default_factory=list)
    resolved_problems: int = 0
    constraint_violations: list[str] = Field(default_factory=list)
    notes: list[str] = Field(default_factory=list)


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
