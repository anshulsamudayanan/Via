"""Analysis runs and findings (Stage 2)."""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Annotated, Any

from pydantic import BaseModel, Field

from via_api.models.enums import AnalysisStatus, FindingStatus
from via_api.schemas.common import APIModel
from via_api.schemas.projects import UserRef
from via_pcb.analysis import Category, Severity, Source, Verification


class AnalysisStart(BaseModel):
    revision_id: uuid.UUID | None = Field(default=None, description="Defaults to the design's current parsed revision")
    checks: list[str] | None = Field(default=None, max_length=100, description="Run only these checks (default: all)")
    options: AnalysisOptions | None = None


class CheckInfo(BaseModel):
    id: str
    version: str
    category: Category
    title: str
    description: str
    source: Source


class CheckRunOut(BaseModel):
    check_id: str
    version: str
    status: str = Field(description="ok | skipped | error")
    finding_count: int = 0
    duration_ms: float = 0.0
    message: str | None = None
    details: dict[str, Any] = Field(default_factory=dict)


class AnalysisRunOut(BaseModel):
    id: uuid.UUID
    design_id: uuid.UUID
    revision_id: uuid.UUID
    revision_number: int
    status: AnalysisStatus
    attempt: int
    config: dict[str, Any]
    checks: list[CheckRunOut]
    summary: dict[str, Any] = Field(description="finding_count, by_severity, checks, duration_seconds")
    analysis_version: str | None
    engine_version: str | None
    design_parser_version: str | None
    design_schema_version: str | None
    error_code: str | None
    error_message: str | None
    triggered_by: UserRef | None
    created_at: datetime
    started_at: datetime | None
    finished_at: datetime | None


class AnalysisRunPage(BaseModel):
    items: list[AnalysisRunOut]
    total: int
    limit: int
    offset: int


class ObjectRefOut(BaseModel):
    kind: str
    id: str
    label: str | None = None


class EvidenceOut(APIModel):
    kind: str
    label: str
    value: str
    numeric_value: float | None
    unit: str | None
    expected: str | None


class FindingOut(APIModel):
    id: uuid.UUID
    run_id: uuid.UUID
    project_id: uuid.UUID
    design_id: uuid.UUID
    revision_id: uuid.UUID
    check_id: str
    check_version: str
    rule: str
    category: Category
    severity: Severity
    source: Source
    verification: Verification
    confidence: float
    title: str
    description: str
    explanation: str
    suggested_resolution: str | None
    objects: list[ObjectRefOut]
    components: list[str]
    nets: list[str]
    region: dict[str, Any] | None
    fingerprint: str
    status: FindingStatus
    status_reason: str | None
    status_changed_at: datetime | None
    inherited: bool = Field(description="Review state carried over from the same issue in an earlier revision")
    created_at: datetime


class ReviewEventOut(APIModel):
    from_status: FindingStatus
    to_status: FindingStatus
    reason: str | None
    carried_over: bool
    actor: UserRef | None
    created_at: datetime


class FindingDetail(FindingOut):
    evidence: list[EvidenceOut]
    history: list[ReviewEventOut]


class FindingPage(BaseModel):
    items: list[FindingOut]
    total: int
    limit: int
    offset: int
    facets: dict[str, dict[str, int]] = Field(description="Counts per severity, status, category and source in the run")


class ReviewRequest(BaseModel):
    status: FindingStatus
    reason: str | None = Field(default=None, max_length=2000)


class CompareOut(BaseModel):
    base_run: AnalysisRunOut
    target_run: AnalysisRunOut
    new: list[FindingOut]
    resolved: list[FindingOut]
    persisting: list[FindingOut]


# --- Manufacturing profiles and analysis options (Milestone 3) -----------------------------------

_MM = Field(gt=0, le=50)


class ProfileValues(BaseModel):
    """Fabrication capabilities in mm (see via_pcb.analysis.profiles)."""

    min_track_width: float = _MM
    min_clearance: float = _MM
    min_drill: float = _MM
    min_via_diameter: float = _MM
    min_annular_ring: float = _MM
    min_hole_to_hole: float = _MM
    min_copper_to_edge: float = _MM
    min_silk_width: float = _MM


class ProfileCreate(BaseModel):
    name: str = Field(min_length=1, max_length=100)
    description: str = Field(default="", max_length=1000)
    values: ProfileValues


class ProfileUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=100)
    description: str | None = Field(default=None, max_length=1000)
    values: ProfileValues | None = None


class ProfileOut(BaseModel):
    key: str = Field(description="Built-in key (via-*) or the profile's id; pass it as options.profile")
    name: str
    description: str
    source: str
    builtin: bool
    values: ProfileValues


class PowerInputs(BaseModel):
    nets: dict[str, Annotated[float, Field(gt=0, le=1000)]] = Field(
        description="Required current in amps per net name", max_length=500
    )
    temperature_rise_c: float = Field(default=10.0, gt=0, le=100)
    copper_thickness_mm: float | None = Field(default=None, gt=0, le=0.5, description="Used when the stackup has none")


class ImpedanceInputs(BaseModel):
    nets: dict[str, Annotated[float, Field(gt=0, le=1000)]] = Field(
        description="Target single-ended impedance in ohms per net name", max_length=500
    )
    tolerance_pct: float = Field(default=10.0, gt=0, le=50)


class AnalysisOptions(BaseModel):
    profile: str | None = Field(
        default=None, max_length=64, description="Manufacturing profile key (default via-conservative)"
    )
    power: PowerInputs | None = None
    impedance: ImpedanceInputs | None = None
    decoupling_max_distance_mm: float | None = Field(default=None, gt=0, le=100)


AnalysisStart.model_rebuild()
