"""Design, revision, file and parsed-PCB schemas."""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any

from pydantic import BaseModel, Field

from via_api.models.enums import DesignFileKind, RevisionStatus
from via_api.schemas.common import APIModel, Name
from via_api.schemas.projects import UserRef


class FileOut(APIModel):
    id: uuid.UUID
    kind: DesignFileKind
    original_filename: str | None
    content_type: str
    size_bytes: int
    sha256: str
    created_at: datetime
    revision_id: uuid.UUID


class ProjectFileOut(FileOut):
    design_id: uuid.UUID
    design_name: str
    revision_number: int


class WarningOut(BaseModel):
    code: str
    message: str


class RevisionOut(APIModel):
    id: uuid.UUID
    design_id: uuid.UUID
    project_id: uuid.UUID
    revision_number: int
    status: RevisionStatus
    source_format: str
    source_sha256: str
    parser_version: str | None
    schema_version: str | None
    imported_at: datetime | None
    error_code: str | None
    error_message: str | None
    warnings: list[WarningOut]
    object_counts: dict[str, Any]
    created_by: UserRef | None
    created_at: datetime
    source_file: FileOut | None


class DesignOut(APIModel):
    id: uuid.UUID
    project_id: uuid.UUID
    name: str
    description: str
    created_by: UserRef | None
    created_at: datetime
    updated_at: datetime
    revision_count: int
    #: Latest successfully parsed revision (what the PCB endpoints show by default).
    current_revision: RevisionOut | None
    #: Most recent upload, whatever its status (shows processing/failure state).
    latest_revision: RevisionOut | None


class DesignDetail(DesignOut):
    revisions: list[RevisionOut]


class DesignUpdate(BaseModel):
    name: Name | None = None
    description: str | None = Field(default=None, max_length=2000)


class ImportResponse(BaseModel):
    design: DesignOut
    revision: RevisionOut


class FormatInfo(BaseModel):
    id: str
    name: str
    extensions: list[str]


class UploadLimits(BaseModel):
    max_upload_bytes: int
    formats: list[FormatInfo]


class GeometryOut(APIModel):
    outline_closed: bool
    min_x: float | None
    min_y: float | None
    max_x: float | None
    max_y: float | None
    width: float | None
    height: float | None
    area: float | None
    thickness: float | None
    copper_layer_count: int


class DesignRef(APIModel):
    id: uuid.UUID
    name: str
    project_id: uuid.UUID


class BoardSummary(BaseModel):
    design: DesignRef
    revision: RevisionOut
    title: str | None
    source: dict[str, Any]
    constraints: dict[str, Any]
    geometry: GeometryOut | None
    stats: dict[str, Any]
    warnings: list[WarningOut]


class ComponentOut(APIModel):
    id: uuid.UUID
    reference: str
    value: str | None
    footprint: str
    layer: str
    side: str
    x: float
    y: float
    rotation: float
    pad_count: int
    attributes: list[str]
    properties: dict[str, Any]


class NetOut(APIModel):
    id: uuid.UUID
    code: int
    name: str
    pad_count: int
    track_count: int
    via_count: int
    track_length: float


class LayerOut(APIModel):
    ordinal: int
    name: str
    kind: str
    side: str
    source_type: str | None
    user_name: str | None
