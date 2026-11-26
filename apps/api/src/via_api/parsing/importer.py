"""Process one uploaded revision: sandboxed parse, then persist the result.

Runs in the worker (``via_api.jobs``). Idempotent: re-running a revision
replaces any rows from an earlier attempt.
"""

from __future__ import annotations

import gzip
import hashlib
import logging
import uuid
from typing import Any

from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from via_api.models import (
    AnalysisRun,
    Design,
    DesignFile,
    DesignRevision,
    PCBComponent,
    PCBGeometry,
    PCBLayer,
    PCBNet,
)
from via_api.models.base import utcnow
from via_api.models.enums import AnalysisKind, AnalysisStatus, DesignFileKind, RevisionStatus
from via_api.parsing.sandbox import ParseOutcome, SandboxLimits, run_parser
from via_api.services import activity
from via_api.storage import ObjectNotFoundError, StorageBackend, StorageError, revision_object_key
from via_pcb import ENGINE_VERSION, SCHEMA_VERSION, PCBDesign

logger = logging.getLogger("via_api.import")

DESIGN_PARSED = "design.parsed"
DESIGN_PARSE_FAILED = "design.parse_failed"


def source_file(db: Session, revision: DesignRevision) -> DesignFile | None:
    return db.scalar(
        select(DesignFile).where(DesignFile.revision_id == revision.id, DesignFile.kind == DesignFileKind.SOURCE)
    )


def import_run(db: Session, revision: DesignRevision) -> AnalysisRun:
    run = db.scalar(
        select(AnalysisRun)
        .where(AnalysisRun.revision_id == revision.id, AnalysisRun.kind == AnalysisKind.PCB_IMPORT)
        .order_by(AnalysisRun.created_at.desc())
    )
    if run is None:
        run = AnalysisRun(
            project_id=revision.project_id, revision_id=revision.id, kind=AnalysisKind.PCB_IMPORT, attempt=0
        )
        db.add(run)
    return run


def mark_failed(db: Session, revision: DesignRevision, code: str, message: str) -> None:
    now = utcnow()
    revision.status = RevisionStatus.FAILED
    revision.error_code = code
    revision.error_message = message
    revision.imported_at = None
    run = import_run(db, revision)
    run.status = AnalysisStatus.FAILED
    run.error_code = code
    run.error_message = message
    run.finished_at = now
    activity.record(
        db,
        DESIGN_PARSE_FAILED,
        actor_id=revision.created_by_id,
        project_id=revision.project_id,
        target_type="revision",
        target_id=revision.id,
        details={"revision": revision.revision_number, "error_code": code},
    )


def _summary(design: PCBDesign) -> dict[str, Any]:
    outline = design.outline
    bbox = design.bbox
    return {
        "title": design.title,
        "source": design.source.model_dump(mode="json", exclude={"sha256"}),
        "constraints": design.constraints.model_dump(mode="json"),
        "geometry": {
            "outline_closed": outline.closed,
            "bbox": bbox.model_dump(mode="json") if bbox else None,
        },
        "warning_count": len(design.warnings),
    }


def _persist_rows(db: Session, revision: DesignRevision, design: PCBDesign, normalized_file: DesignFile) -> None:
    rid = revision.id
    for model in (PCBComponent, PCBNet, PCBLayer, PCBGeometry):
        db.execute(delete(model).where(model.revision_id == rid))
    db.add_all(
        PCBLayer(
            revision_id=rid,
            ordinal=layer.index,
            name=layer.name,
            kind=layer.kind.value,
            side=layer.side.value,
            source_type=layer.source_type,
            user_name=layer.user_name,
        )
        for layer in design.layers
    )
    codes = {n.name: n.code for n in design.nets}
    db.add_all(
        PCBNet(
            revision_id=rid,
            code=codes.get(s.name, 0),
            name=s.name,
            pad_count=s.pad_count,
            track_count=s.track_count,
            via_count=s.via_count,
            track_length=s.track_length,
        )
        for s in design.net_stats
    )
    db.add_all(
        PCBComponent(
            revision_id=rid,
            reference=c.reference,
            value=c.value,
            footprint=c.footprint,
            layer=c.layer,
            side=c.side.value,
            x=c.position.x,
            y=c.position.y,
            rotation=c.rotation,
            pad_count=len(c.pads),
            attributes=c.attributes,
            properties=c.properties,
        )
        for c in design.components
    )
    bbox = design.bbox
    stats = design.stats
    db.add(
        PCBGeometry(
            revision_id=rid,
            outline_closed=design.outline.closed,
            min_x=bbox.min_x if bbox else None,
            min_y=bbox.min_y if bbox else None,
            max_x=bbox.max_x if bbox else None,
            max_y=bbox.max_y if bbox else None,
            width=stats.board_width,
            height=stats.board_height,
            area=stats.board_area,
            thickness=stats.board_thickness,
            copper_layer_count=stats.copper_layer_count,
            normalized_file_id=normalized_file.id,
        )
    )


def process_revision(
    db: Session,
    storage: StorageBackend,
    revision_id: uuid.UUID,
    limits: SandboxLimits,
    *,
    parse: Any = run_parser,
    attempt: int = 1,
    job_id: str | None = None,
) -> DesignRevision | None:
    """Parse and persist one revision. Commits. Returns the revision (or None if it vanished).

    ``attempt`` and ``job_id`` identify this try for the job reaper (see ``via_api.jobs``).
    """
    revision = db.get(DesignRevision, revision_id)
    if revision is None:  # deleted before the job ran
        logger.info("Revision %s no longer exists; skipping", revision_id)
        return None
    run = import_run(db, revision)
    # Re-importing an already parsed revision (e.g. after a parser upgrade) must not change which
    # revision is current: that is the user's choice (uploads, change sets, rollbacks).
    first_import = revision.imported_at is None
    revision.status = RevisionStatus.PROCESSING
    revision.error_code = revision.error_message = None
    run.status = AnalysisStatus.RUNNING
    run.started_at = run.heartbeat_at = utcnow()
    run.engine_version = ENGINE_VERSION
    run.attempt = attempt
    run.job_id = job_id
    run.error_code = run.error_message = None
    run.finished_at = None
    db.commit()

    source = source_file(db, revision)
    try:
        if source is None:
            raise ObjectNotFoundError("source file row missing")
        data = storage.get(source.storage_key)
    except (ObjectNotFoundError, StorageError) as exc:
        logger.error("Source for revision %s unavailable: %s", revision_id, exc)
        mark_failed(db, revision, "source_unavailable", "The uploaded file could not be read from storage.")
        db.commit()
        return revision

    if hashlib.sha256(data).hexdigest() != revision.source_sha256:
        mark_failed(db, revision, "integrity_error", "The stored file does not match the uploaded file.")
        db.commit()
        return revision

    outcome: ParseOutcome = parse(data, source.original_filename, limits)
    if not outcome.ok or outcome.design is None:
        mark_failed(db, revision, outcome.error_code or "parse_failed", outcome.error_message or "Parsing failed.")
        db.commit()
        return revision
    design = outcome.design

    # Store the full normalized design (gzipped JSON) alongside the source.
    payload = gzip.compress(design.model_dump_json().encode(), compresslevel=6)
    key = revision_object_key(revision.project_id, revision.id, "normalized.json.gz")
    try:
        storage.put(key, payload, content_type="application/gzip")
    except StorageError as exc:
        logger.error("Could not store normalized design for %s: %s", revision_id, exc)
        mark_failed(db, revision, "storage_error", "The parsed design could not be saved. Try uploading again.")
        db.commit()
        return revision
    normalized = db.scalar(select(DesignFile).where(DesignFile.storage_key == key))
    if normalized is None:
        normalized = DesignFile(
            revision_id=revision.id,
            project_id=revision.project_id,
            kind=DesignFileKind.NORMALIZED,
            storage_key=key,
            original_filename=None,
            content_type="application/gzip",
            size_bytes=len(payload),
            sha256=hashlib.sha256(payload).hexdigest(),
        )
        db.add(normalized)
    else:
        normalized.size_bytes = len(payload)
        normalized.sha256 = hashlib.sha256(payload).hexdigest()
    db.flush()

    _persist_rows(db, revision, design, normalized)
    now = utcnow()
    revision.status = RevisionStatus.READY
    revision.parser_version = ENGINE_VERSION
    revision.schema_version = SCHEMA_VERSION
    revision.imported_at = now
    revision.warnings = [w.model_dump(mode="json") for w in design.warnings]
    revision.object_counts = design.stats.model_dump(mode="json")
    revision.summary = _summary(design)
    run.status = AnalysisStatus.SUCCEEDED
    run.finished_at = now
    run.result_summary = {
        "duration_seconds": round(outcome.duration_seconds, 3),
        "warnings": len(design.warnings),
        "components": design.stats.component_count,
        "nets": design.stats.net_count,
    }
    parent = db.get(Design, revision.design_id)
    if parent is not None:
        current = db.get(DesignRevision, parent.current_revision_id) if parent.current_revision_id else None
        if current is None or (first_import and current.revision_number <= revision.revision_number):
            parent.current_revision_id = revision.id
        parent.updated_at = now
    activity.record(
        db,
        DESIGN_PARSED,
        actor_id=revision.created_by_id,
        project_id=revision.project_id,
        target_type="revision",
        target_id=revision.id,
        details={
            "revision": revision.revision_number,
            "components": design.stats.component_count,
            "nets": design.stats.net_count,
            "warnings": len(design.warnings),
        },
    )
    db.commit()
    return revision
