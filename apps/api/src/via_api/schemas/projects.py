"""Organization, project, membership and activity schemas."""

from __future__ import annotations

import uuid
from datetime import datetime
from enum import StrEnum
from typing import Annotated, Any

from pydantic import AfterValidator, BaseModel, Field

from via_api.models.enums import AnalysisStatus, OrganizationRole, ProjectRole, ProjectVisibility, RevisionStatus
from via_api.schemas.common import APIModel, Email, Name


def _clean_description(value: str) -> str:
    value = value.strip()
    if any(ord(c) < 32 and c not in "\n\t" for c in value):
        raise ValueError("Control characters are not allowed.")
    return value


Description = Annotated[str, AfterValidator(_clean_description), Field(max_length=2000)]


class UserRef(APIModel):
    id: uuid.UUID
    display_name: str


class OrganizationRef(APIModel):
    id: uuid.UUID
    name: str
    is_personal: bool


class OrganizationOut(APIModel):
    id: uuid.UUID
    name: str
    slug: str
    is_personal: bool
    role: OrganizationRole
    created_at: datetime


class OrganizationCreate(BaseModel):
    name: Name


class OrganizationMemberOut(APIModel):
    user: UserRef
    role: OrganizationRole
    joined_at: datetime


class ProjectCreate(BaseModel):
    name: Name
    description: Description = ""
    #: Defaults to the caller's personal organization.
    organization_id: uuid.UUID | None = None
    visibility: ProjectVisibility = ProjectVisibility.PRIVATE


class ProjectUpdate(BaseModel):
    name: Name | None = None
    description: Description | None = None
    visibility: ProjectVisibility | None = None


class LatestImport(BaseModel):
    """The project's most recent upload (any design), whatever its status."""

    design_id: uuid.UUID
    design_name: str
    revision_number: int
    status: RevisionStatus
    at: datetime


class LatestAnalysis(BaseModel):
    """The project's most recent analysis run (any design)."""

    design_id: uuid.UUID
    design_name: str
    status: AnalysisStatus
    at: datetime
    #: Only for succeeded runs.
    finding_count: int | None = None


class ProjectOut(APIModel):
    id: uuid.UUID
    name: str
    description: str
    visibility: ProjectVisibility
    organization: OrganizationRef
    owner: UserRef
    my_role: ProjectRole
    design_count: int
    latest_import: LatestImport | None = None
    latest_analysis: LatestAnalysis | None = None
    archived_at: datetime | None
    created_at: datetime
    updated_at: datetime


class ProjectStatusFilter(StrEnum):
    ACTIVE = "active"
    ARCHIVED = "archived"
    ALL = "all"


class ProjectSort(StrEnum):
    UPDATED = "updated"
    CREATED = "created"
    NAME = "name"


class ProjectMemberOut(APIModel):
    user: UserRef
    role: ProjectRole
    added_at: datetime


class MemberAdd(BaseModel):
    email: Email
    role: ProjectRole = ProjectRole.VIEWER


class MemberUpdate(BaseModel):
    role: ProjectRole


class ProjectRef(APIModel):
    id: uuid.UUID
    name: str


class ActivityOut(APIModel):
    id: uuid.UUID
    action: str
    created_at: datetime
    actor: UserRef | None
    project: ProjectRef | None
    target_type: str | None
    target_id: uuid.UUID | None
    details: dict[str, Any]


class ProjectSummary(BaseModel):
    """Counts for the dashboard (all derived from real rows)."""

    active: int
    archived: int
    #: Designs in active projects.
    designs: int = 0
    #: Uploads (revisions) and completed analysis runs in active projects over the last 7 days.
    imports_7d: int = 0
    analyses_7d: int = 0
