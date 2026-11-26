"""Cross-project views behind the sidebar's Analysis and Components pages."""

from __future__ import annotations

import uuid
from datetime import datetime
from enum import StrEnum
from typing import Any

from pydantic import BaseModel, Field

from via_api.models.enums import AnalysisStatus, FindingStatus
from via_api.schemas.projects import ProjectRef, UserRef
from via_pcb.analysis import Category, Severity, Source, Verification


class NamedRef(BaseModel):
    id: uuid.UUID
    name: str


class RunListItem(BaseModel):
    id: uuid.UUID
    status: AnalysisStatus
    design: NamedRef
    project: ProjectRef
    project_archived: bool
    revision_id: uuid.UUID
    revision_number: int
    #: Only for succeeded runs.
    finding_count: int | None
    by_severity: dict[str, int]
    error_code: str | None
    triggered_by: UserRef | None
    created_at: datetime
    finished_at: datetime | None


class RunListPage(BaseModel):
    items: list[RunListItem]
    total: int
    limit: int
    offset: int


class FindingListItem(BaseModel):
    id: uuid.UUID
    run_id: uuid.UUID
    design: NamedRef
    project: ProjectRef
    revision_id: uuid.UUID
    revision_number: int
    check_id: str
    rule: str
    category: Category
    severity: Severity
    source: Source
    verification: Verification
    title: str
    status: FindingStatus
    components: list[str]
    nets: list[str]
    created_at: datetime


class FindingListPage(BaseModel):
    items: list[FindingListItem]
    total: int
    limit: int
    offset: int
    #: Counts per severity over the same filters, ignoring the severity filter.
    by_severity: dict[str, int]
    #: How many designs have a succeeded analysis in scope (the denominator for the counts).
    designs_analysed: int


class FindingStatusFilter(StrEnum):
    OPEN = "open"
    REVIEWED = "reviewed"
    DISMISSED = "dismissed"
    ALL = "all"


class PartSort(StrEnum):
    PLACEMENTS = "placements"
    VALUE = "value"
    FOOTPRINT = "footprint"


class PartListItem(BaseModel):
    """One (value, footprint) pair as placed in the current revisions of your designs."""

    value: str | None
    footprint: str
    placements: int
    design_count: int
    #: Up to 12 reference designators, sorted.
    references: list[str]
    references_truncated: bool
    #: Up to 5 designs using the part.
    designs: list[dict[str, Any]] = Field(description="[{id, name, project_id}]")


class PartListPage(BaseModel):
    items: list[PartListItem]
    total: int
    limit: int
    offset: int
    #: Totals over the same filters.
    placements: int
    designs: int
