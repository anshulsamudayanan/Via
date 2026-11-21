"""/api/v1/files: uploaded source files (metadata and download)."""

from __future__ import annotations

import uuid
from urllib.parse import quote

from fastapi import APIRouter, Response
from sqlalchemy import select

from via_api.deps import DB, CurrentAuth, Storage
from via_api.errors import APIError, error_responses, not_found
from via_api.models import Design, DesignFile, DesignRevision
from via_api.models.enums import DesignFileKind
from via_api.schemas.pcb import ProjectFileOut
from via_api.services import access

router = APIRouter(prefix="/files", tags=["files"])


@router.get("", response_model=list[ProjectFileOut], responses=error_responses(401, 404))
def list_files(project_id: uuid.UUID, db: DB, ctx: CurrentAuth) -> list[ProjectFileOut]:
    """Original uploads in a project, newest first. Contents live in object storage, not the database."""
    access.get_project(db, ctx.user.id, project_id)
    rows = db.execute(
        select(DesignFile, DesignRevision, Design)
        .join(DesignRevision, DesignRevision.id == DesignFile.revision_id)
        .join(Design, Design.id == DesignRevision.design_id)
        .where(DesignFile.project_id == project_id, DesignFile.kind == DesignFileKind.SOURCE)
        .order_by(DesignFile.created_at.desc())
    ).all()
    return [
        ProjectFileOut(
            **{
                c: getattr(f, c)
                for c in (
                    "id",
                    "kind",
                    "original_filename",
                    "content_type",
                    "size_bytes",
                    "sha256",
                    "created_at",
                    "revision_id",
                )
            },
            design_id=d.id,
            design_name=d.name,
            revision_number=r.revision_number,
        )
        for f, r, d in rows
    ]


@router.get(
    "/{file_id}/download",
    response_class=Response,
    responses={**error_responses(401, 404, 503), 200: {"content": {"application/octet-stream": {}}}},
)
def download_file(file_id: uuid.UUID, db: DB, storage: Storage, ctx: CurrentAuth) -> Response:
    """Download an original upload. Served as an attachment, never rendered inline."""
    file = db.get(DesignFile, file_id)
    if file is None or file.kind != DesignFileKind.SOURCE:
        raise not_found("File")
    try:
        access.get_project(db, ctx.user.id, file.project_id)
    except APIError as exc:
        if exc.status_code == 404:
            raise not_found("File") from exc
        raise
    try:
        data = storage.get(file.storage_key)
    except Exception as exc:
        raise APIError(503, "storage_unavailable", "The file could not be loaded from storage.") from exc
    name = file.original_filename or "design.kicad_pcb"
    ascii_name = name.encode("ascii", "replace").decode().replace('"', "_")
    return Response(
        content=data,
        media_type="application/octet-stream",
        headers={
            "Content-Disposition": f"attachment; filename=\"{ascii_name}\"; filename*=UTF-8''{quote(name)}",
            "Cache-Control": "private, no-store",
        },
    )
