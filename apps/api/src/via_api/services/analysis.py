"""Analysis runs and findings: start, execute (worker), review, query, compare.

Results are immutable history. Every run analyses one exact revision and records the
analysis, engine, parser and schema versions plus each check's version and outcome.
Re-running creates a new run; earlier runs and their findings stay as they were. Only a
finding's review state changes, with every change appended to ``finding_review_events``.

Review carry-over: when a new run reports the same issue (same design and fingerprint)
as an earlier finding that a person reviewed or dismissed, the new finding starts in that
state, with ``inherited_from_id`` and a ``carried_over`` event, so users don't re-dismiss
the same thing on every revision. Reopening is always possible.
"""

from __future__ import annotations

import gzip
import logging
import uuid
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from via_api.errors import APIError, not_found
from via_api.models import (
    AnalysisFinding,
    AnalysisRun,
    Design,
    DesignFile,
    DesignRevision,
    FindingEvidence,
    FindingReviewEvent,
    PCBGeometry,
)
from via_api.models.base import utcnow
from via_api.models.enums import AnalysisKind, AnalysisStatus, FindingStatus, ProjectRole, RevisionStatus
from via_api.services import access, activity
from via_api.services import designs as design_svc
from via_api.services.activity import ClientInfo
from via_api.services.auth import AuthContext
from via_api.storage import ObjectNotFoundError, StorageBackend, StorageError
from via_pcb import SCHEMA_VERSION, PCBDesign
from via_pcb.analysis import ANALYSIS_VERSION, AnalysisResult, default_engine, default_registry

logger = logging.getLogger("via_api.analysis")

ANALYSIS_REQUESTED = "analysis.requested"
ANALYSIS_COMPLETED = "analysis.completed"
ANALYSIS_FAILED = "analysis.failed"
FINDING_REVIEWED = "finding.reviewed"

_ACTIVE = (AnalysisStatus.QUEUED, AnalysisStatus.RUNNING)


def analysis_job_id(run_id: uuid.UUID | str, attempt: int) -> str:
    return f"analysis-{run_id}-a{attempt}"


# ----------------------------------------------------------------- starting


def normalize_config(checks: list[str] | None) -> dict[str, Any]:
    known = {c.id for c in default_registry().all()}
    if checks is None:
        return {}
    unknown = sorted(set(checks) - known)
    if unknown:
        raise APIError(422, "unknown_check", f"Unknown check(s): {', '.join(unknown)}.", {"known": sorted(known)})
    return {"checks": sorted(set(checks))}


def start_analysis(
    db: Session,
    ctx: AuthContext,
    design_id: uuid.UUID,
    revision_id: uuid.UUID | None,
    checks: list[str] | None,
    client: ClientInfo,
) -> tuple[AnalysisRun, bool]:
    """Create a queued run, or return the identical run already queued/running. Returns (run, created)."""
    design, project, _ = design_svc.get_design(db, ctx.user.id, design_id, ProjectRole.EDITOR, action="run analyses")
    access.ensure_active(project)
    revision = design_svc.resolve_parsed_revision(db, design, revision_id)
    config = normalize_config(checks)
    existing = db.scalar(
        select(AnalysisRun)
        .where(
            AnalysisRun.revision_id == revision.id,
            AnalysisRun.kind == AnalysisKind.PCB_ANALYSIS,
            AnalysisRun.status.in_(_ACTIVE),
        )
        .order_by(AnalysisRun.created_at.desc())
    )
    if existing is not None and existing.config == config:
        return existing, False
    run = AnalysisRun(
        project_id=project.id,
        revision_id=revision.id,
        kind=AnalysisKind.PCB_ANALYSIS,
        status=AnalysisStatus.QUEUED,
        config=config,
        attempt=1,
        triggered_by_id=ctx.user.id,
    )
    db.add(run)
    db.flush()
    run.job_id = analysis_job_id(run.id, 1)
    activity.record(
        db,
        ANALYSIS_REQUESTED,
        actor_id=ctx.user.id,
        client=client,
        project_id=project.id,
        target_type="analysis_run",
        target_id=run.id,
        details={"design": design.name, "revision": revision.revision_number},
    )
    return run, True


def fail_run(db: Session, run: AnalysisRun, code: str, message: str) -> None:
    run.status = AnalysisStatus.FAILED
    run.error_code = code
    run.error_message = message
    run.finished_at = utcnow()
    activity.record(
        db,
        ANALYSIS_FAILED,
        actor_id=run.triggered_by_id,
        project_id=run.project_id,
        target_type="analysis_run",
        target_id=run.id,
        details={"error_code": code},
    )


# ----------------------------------------------------------------- executing (worker)


def _load_design(db: Session, storage: StorageBackend, revision: DesignRevision) -> PCBDesign:
    geometry = db.scalar(select(PCBGeometry).where(PCBGeometry.revision_id == revision.id))
    file = db.get(DesignFile, geometry.normalized_file_id) if geometry and geometry.normalized_file_id else None
    if file is None:
        raise ObjectNotFoundError("normalized design missing")
    return PCBDesign.model_validate_json(gzip.decompress(storage.get(file.storage_key)))


def _needs_reimport(design: PCBDesign) -> bool:
    """Designs parsed before schema 1.1 have no object ids, which findings need."""
    major, minor = (int(p) for p in design.schema_version.split(".")[:2])
    cur_major, cur_minor = (int(p) for p in SCHEMA_VERSION.split(".")[:2])
    return (major, minor) < (cur_major, cur_minor)


def process_analysis(
    db: Session,
    storage: StorageBackend,
    run_id: uuid.UUID,
    *,
    reimport: Any,
    drc: Any = None,
    attempt: int = 1,
    job_id: str | None = None,
) -> AnalysisRun | None:
    """Execute one analysis run. Commits.

    ``reimport(revision_id)`` re-parses an outdated revision; ``drc(revision)`` returns the input
    for the ``kicad_drc`` check (KiCad's report or an error), or is None when not available.
    """
    run = db.get(AnalysisRun, run_id)
    if run is None or run.kind != AnalysisKind.PCB_ANALYSIS:
        return None
    if run.status == AnalysisStatus.SUCCEEDED:
        return run  # duplicate delivery
    revision = db.get(DesignRevision, run.revision_id) if run.revision_id else None
    if revision is None:
        return None
    run.status = AnalysisStatus.RUNNING
    run.started_at = run.heartbeat_at = utcnow()
    run.attempt = attempt
    run.job_id = job_id or run.job_id
    run.error_code = run.error_message = None
    run.finished_at = None
    run.analysis_version = ANALYSIS_VERSION
    db.commit()

    if revision.status != RevisionStatus.READY:
        fail_run(db, run, "revision_not_ready", "The revision isn't parsed, so it can't be analysed.")
        db.commit()
        return run
    try:
        design = _load_design(db, storage, revision)
        if _needs_reimport(design):
            logger.info("Revision %s was parsed with schema %s; re-importing", revision.id, design.schema_version)
            reimport(revision.id)
            db.refresh(revision)
            if revision.status != RevisionStatus.READY:
                fail_run(db, run, "reimport_failed", "The design couldn't be re-parsed with the current parser.")
                db.commit()
                return run
            design = _load_design(db, storage, revision)
    except (ObjectNotFoundError, StorageError, OSError, ValueError) as exc:
        logger.error("Design for analysis run %s unavailable: %s", run.id, exc)
        fail_run(db, run, "design_unavailable", "The parsed design couldn't be loaded. Try re-uploading it.")
        db.commit()
        return run

    only = set(run.config.get("checks", [])) or None
    options = dict(run.config.get("options") or {})
    if drc is not None and (only is None or "kicad_drc" in only):
        options["kicad_drc"] = drc(revision)
    result = default_engine().run(design, options=options, only=only)
    persist_result(db, run, revision, result)
    run.design_parser_version = design.engine_version
    run.design_schema_version = design.schema_version
    db.commit()
    return run


def persist_result(db: Session, run: AnalysisRun, revision: DesignRevision, result: AnalysisResult) -> None:
    now = utcnow()
    # Same issue, earlier run, last decided by a person: carry that decision over.
    fingerprints = {f.fingerprint for f in result.findings}
    decided: dict[str, AnalysisFinding] = {}
    if fingerprints:
        previous = db.scalars(
            select(AnalysisFinding)
            .where(
                AnalysisFinding.design_id == revision.design_id,
                AnalysisFinding.fingerprint.in_(fingerprints),
                AnalysisFinding.run_id != run.id,
                AnalysisFinding.status_changed_at.is_not(None),
            )
            .order_by(AnalysisFinding.status_changed_at.desc())
        ).all()
        for p in previous:
            decided.setdefault(p.fingerprint, p)
    versions = {c.check_id: c.version for c in result.checks}
    counts = {s: 0 for s in ("critical", "high", "medium", "low", "info")}
    for f in result.findings:
        counts[f.severity.value] += 1
        row = AnalysisFinding(
            run_id=run.id,
            project_id=run.project_id,
            design_id=revision.design_id,
            revision_id=revision.id,
            check_id=f.check_id,
            check_version=versions.get(f.check_id, ""),
            rule=f.rule,
            category=f.category,
            severity=f.severity,
            severity_rank=f.severity.rank,
            source=f.source,
            verification=f.verification,
            confidence=f.confidence,
            title=f.title[:300],
            description=f.description,
            explanation=f.explanation,
            suggested_resolution=f.suggested_resolution,
            objects=[o.model_dump(mode="json") for o in f.objects],
            components=f.components,
            nets=f.nets,
            region=f.region.model_dump(mode="json") if f.region else None,
            fingerprint=f.fingerprint,
        )
        prior = decided.get(f.fingerprint)
        if prior is not None and prior.status != FindingStatus.OPEN:
            row.status = prior.status
            row.status_reason = prior.status_reason
            row.status_changed_at = now
            row.status_changed_by_id = prior.status_changed_by_id
            row.inherited_from_id = prior.id
        db.add(row)
        db.flush()
        for i, e in enumerate(f.evidence):
            db.add(
                FindingEvidence(
                    finding_id=row.id,
                    ordinal=i,
                    kind=e.kind,
                    label=e.label[:200],
                    value=e.value,
                    numeric_value=e.numeric_value,
                    unit=e.unit,
                    expected=e.expected,
                )
            )
        if row.inherited_from_id is not None and prior is not None:
            prior_rev = db.get(DesignRevision, prior.revision_id)
            db.add(
                FindingReviewEvent(
                    finding_id=row.id,
                    actor_id=None,
                    from_status=FindingStatus.OPEN,
                    to_status=row.status,
                    reason=f"Carried over from revision {prior_rev.revision_number if prior_rev else '?'}: "
                    f"{prior.status_reason or prior.status.value}",
                    carried_over=True,
                )
            )
    run.checks = [c.model_dump(mode="json") for c in result.checks]
    run.status = AnalysisStatus.SUCCEEDED
    run.finished_at = now
    run.engine_version = result.engine_version
    run.result_summary = {
        "finding_count": len(result.findings),
        "by_severity": counts,
        "checks": {s: sum(1 for c in result.checks if c.status.value == s) for s in ("ok", "skipped", "error")},
        "duration_seconds": round((now - run.started_at).total_seconds(), 3) if run.started_at else None,
    }
    activity.record(
        db,
        ANALYSIS_COMPLETED,
        actor_id=run.triggered_by_id,
        project_id=run.project_id,
        target_type="analysis_run",
        target_id=run.id,
        details={"revision": revision.revision_number, "findings": len(result.findings), **counts},
    )


# ----------------------------------------------------------------- reading


def get_run(db: Session, user_id: uuid.UUID, run_id: uuid.UUID) -> AnalysisRun:
    run = db.get(AnalysisRun, run_id)
    if run is None or run.kind != AnalysisKind.PCB_ANALYSIS:
        raise not_found("Analysis run")
    try:
        access.get_project(db, user_id, run.project_id)
    except APIError as exc:
        if exc.status_code == 404:
            raise not_found("Analysis run") from exc
        raise
    return run


def get_finding(
    db: Session, user_id: uuid.UUID, finding_id: uuid.UUID, minimum: ProjectRole = ProjectRole.VIEWER
) -> AnalysisFinding:
    finding = db.get(AnalysisFinding, finding_id)
    if finding is None:
        raise not_found("Finding")
    try:
        access.get_project(db, user_id, finding.project_id, minimum, action="review findings")
    except APIError as exc:
        if exc.status_code == 404:
            raise not_found("Finding") from exc
        raise
    return finding


def list_runs(db: Session, design: Design, limit: int, offset: int) -> tuple[list[AnalysisRun], int]:
    base = (
        select(AnalysisRun)
        .join(DesignRevision, DesignRevision.id == AnalysisRun.revision_id)
        .where(DesignRevision.design_id == design.id, AnalysisRun.kind == AnalysisKind.PCB_ANALYSIS)
    )
    total = db.scalar(select(func.count()).select_from(base.subquery())) or 0
    rows = db.scalars(base.order_by(AnalysisRun.created_at.desc()).limit(limit).offset(offset)).all()
    return list(rows), total


# ----------------------------------------------------------------- reviewing


def review(
    db: Session,
    ctx: AuthContext,
    finding: AnalysisFinding,
    status: FindingStatus,
    reason: str | None,
    client: ClientInfo,
) -> AnalysisFinding:
    reason = (reason or "").strip() or None
    if status == FindingStatus.DISMISSED and not reason:
        raise APIError(422, "reason_required", "Say why you're dismissing this finding.")
    if status == finding.status and reason == finding.status_reason:
        return finding
    db.add(
        FindingReviewEvent(
            finding_id=finding.id, actor_id=ctx.user.id, from_status=finding.status, to_status=status, reason=reason
        )
    )
    finding.status = status
    finding.status_reason = reason
    finding.status_changed_at = utcnow()
    finding.status_changed_by_id = ctx.user.id
    finding.inherited_from_id = None  # a person decided now
    activity.record(
        db,
        FINDING_REVIEWED,
        actor_id=ctx.user.id,
        client=client,
        project_id=finding.project_id,
        target_type="finding",
        target_id=finding.id,
        details={"status": status.value, "check": finding.check_id, "rule": finding.rule},
    )
    return finding


# ----------------------------------------------------------------- comparing


def compare(db: Session, base: AnalysisRun, target: AnalysisRun) -> dict[str, list[AnalysisFinding]]:
    """Group findings of two runs of the same design into new, resolved and persisting, by fingerprint."""
    base_rev = db.get(DesignRevision, base.revision_id)
    target_rev = db.get(DesignRevision, target.revision_id)
    if base_rev is None or target_rev is None or base_rev.design_id != target_rev.design_id:
        raise APIError(422, "different_designs", "Both runs must analyse revisions of the same design.")
    for r in (base, target):
        if r.status != AnalysisStatus.SUCCEEDED:
            raise APIError(409, "run_not_finished", "Both runs must have finished successfully.")

    def by_fp(run: AnalysisRun) -> dict[str, AnalysisFinding]:
        rows = db.scalars(
            select(AnalysisFinding)
            .where(AnalysisFinding.run_id == run.id)
            .order_by(AnalysisFinding.severity_rank, AnalysisFinding.title)
        ).all()
        return {f.fingerprint: f for f in rows}

    a, b = by_fp(base), by_fp(target)
    return {
        "new": [f for fp, f in b.items() if fp not in a],
        "resolved": [f for fp, f in a.items() if fp not in b],
        "persisting": [f for fp, f in b.items() if fp in a],
    }
