# ruff: noqa: E501
"""Optimization runs in the API: start, execute (worker), decide on candidates.

Runs are ``analysis_runs`` rows with ``kind = pcb_optimization`` (so they share the job lifecycle:
heartbeat, reaper, retries). Candidates and their explicit changes are stored; nothing touches the
original design. Accepting a candidate records a decision; a change set (services/changes.py) turns
accepted, exportable changes into a new revision and an exported file.
"""

from __future__ import annotations

import uuid
from typing import Any

from sqlalchemy import delete, select
from sqlalchemy.orm import Session
from via_opt import OPTIMIZER_VERSION, Constraints, Objective, optimize

from via_api.errors import APIError, not_found
from via_api.models import AnalysisRun, DesignChange, DesignRevision, OptimizationCandidate
from via_api.models.base import utcnow
from via_api.models.enums import AnalysisKind, AnalysisStatus, ProjectRole, RevisionStatus
from via_api.services import access, activity
from via_api.services import designs as design_svc
from via_api.services.activity import ClientInfo
from via_api.services.analysis import _load_design, _needs_reimport, fail_run, resolve_profile
from via_api.services.auth import AuthContext
from via_api.storage import ObjectNotFoundError, StorageBackend, StorageError

OPTIMIZATION_REQUESTED = "optimization.requested"
OPTIMIZATION_COMPLETED = "optimization.completed"
CANDIDATE_DECIDED = "optimization.candidate_decided"
_ACTIVE = (AnalysisStatus.QUEUED, AnalysisStatus.RUNNING)


def optimization_job_id(run_id: uuid.UUID | str, attempt: int) -> str:
    return f"optimization-{run_id}-a{attempt}"


def start(
    db: Session,
    ctx: AuthContext,
    design_id: uuid.UUID,
    objectives: list[Objective],
    constraints: Constraints,
    options: dict[str, Any] | None,
    client: ClientInfo,
) -> tuple[AnalysisRun, bool]:
    design, project, _ = design_svc.get_design(
        db, ctx.user.id, design_id, ProjectRole.EDITOR, action="run optimizations"
    )
    access.ensure_active(project)
    revision = design_svc.resolve_parsed_revision(db, design, None)
    run_options = {k: v for k, v in (options or {}).items() if v is not None and k != "profile"}
    run_options["manufacturing_profile"] = resolve_profile(db, project.id, (options or {}).get("profile"))
    config = {
        "objectives": sorted({o.value for o in objectives}),
        "constraints": constraints.model_dump(),
        "options": run_options,
    }
    # Serialize starts on this revision so identical concurrent requests share one run.
    db.execute(select(DesignRevision.id).where(DesignRevision.id == revision.id).with_for_update())
    existing = db.scalar(select(AnalysisRun).where(AnalysisRun.revision_id == revision.id, AnalysisRun.kind == AnalysisKind.PCB_OPTIMIZATION,
                                                   AnalysisRun.status.in_(_ACTIVE)).order_by(AnalysisRun.created_at.desc()))  # fmt: skip
    if existing is not None and existing.config == config:
        return existing, False
    run = AnalysisRun(project_id=project.id, revision_id=revision.id, kind=AnalysisKind.PCB_OPTIMIZATION, status=AnalysisStatus.QUEUED,
                      config=config, attempt=1, triggered_by_id=ctx.user.id)  # fmt: skip
    db.add(run)
    db.flush()
    run.job_id = optimization_job_id(run.id, 1)
    activity.record(db, OPTIMIZATION_REQUESTED, actor_id=ctx.user.id, client=client, project_id=project.id,
                    target_type="analysis_run", target_id=run.id, details={"objectives": config["objectives"]})  # fmt: skip
    return run, True


def process(
    db: Session,
    storage: StorageBackend,
    run_id: uuid.UUID,
    *,
    reimport: Any,
    attempt: int = 1,
    job_id: str | None = None,
) -> AnalysisRun | None:
    run = db.get(AnalysisRun, run_id)
    if run is None or run.kind != AnalysisKind.PCB_OPTIMIZATION:
        return None
    if run.status == AnalysisStatus.SUCCEEDED:
        return run
    revision = db.get(DesignRevision, run.revision_id) if run.revision_id else None
    if revision is None:
        return None
    run.status = AnalysisStatus.RUNNING
    run.started_at = run.heartbeat_at = utcnow()
    run.attempt, run.job_id = attempt, job_id or run.job_id
    run.error_code = run.error_message = None
    run.analysis_version = OPTIMIZER_VERSION
    db.commit()
    if revision.status != RevisionStatus.READY:
        fail_run(db, run, "revision_not_ready", "The revision isn't parsed, so it can't be optimized.")
        db.commit()
        return run
    try:
        design = _load_design(db, storage, revision)
        if _needs_reimport(design):
            reimport(revision.id)
            db.refresh(revision)
            design = _load_design(db, storage, revision)
    except (ObjectNotFoundError, StorageError, OSError, ValueError):
        fail_run(db, run, "design_unavailable", "The parsed design couldn't be loaded. Try re-uploading it.")
        db.commit()
        return run
    cfg = run.config
    result = optimize(
        design,
        [Objective(o) for o in cfg["objectives"]],
        Constraints.model_validate(cfg["constraints"]),
        cfg.get("options"),
    )
    db.execute(
        delete(DesignChange).where(
            DesignChange.candidate_id.in_(
                select(OptimizationCandidate.id).where(OptimizationCandidate.run_id == run.id)
            )
        )
    )
    db.execute(delete(OptimizationCandidate).where(OptimizationCandidate.run_id == run.id))
    for c in result.candidates:
        row = OptimizationCandidate(
            run_id=run.id, project_id=run.project_id, design_id=revision.design_id, revision_id=revision.id, key=c.key,
            algorithm=c.algorithm, algorithm_version=c.algorithm_version, objectives=c.objectives, title=c.title, summary=c.summary,
            metrics_before=c.metrics_before, metrics_after=c.metrics_after, expected_benefits=c.expected_benefits,
            trade_offs=c.trade_offs, validation=c.validation.model_dump(mode="json"), pareto=c.key in result.pareto,
            status=c.status.value, details=c.details,
        )  # fmt: skip
        db.add(row)
        db.flush()
        for i, ch in enumerate(c.changes):
            db.add(DesignChange(candidate_id=row.id, project_id=run.project_id, design_id=revision.design_id, revision_id=revision.id,
                                ordinal=i, kind=ch.kind.value, target=ch.target.model_dump(), before=ch.before, after=ch.after,
                                reason=ch.reason, source=ch.source, finding_ids=ch.finding_ids, exportable=ch.exportable))  # fmt: skip
    now = utcnow()
    run.status, run.finished_at = AnalysisStatus.SUCCEEDED, now
    run.design_parser_version, run.design_schema_version = design.engine_version, design.schema_version
    run.result_summary = {"baseline": result.baseline, "pareto": result.pareto, "notes": result.notes, "candidate_count": len(result.candidates),
                          "duration_seconds": round((now - run.started_at).total_seconds(), 3) if run.started_at else None}  # fmt: skip
    activity.record(db, OPTIMIZATION_COMPLETED, actor_id=run.triggered_by_id, project_id=run.project_id, target_type="analysis_run",
                    target_id=run.id, details={"candidates": len(result.candidates)})  # fmt: skip
    db.commit()
    return run


def get_run(db: Session, user_id: uuid.UUID, run_id: uuid.UUID) -> AnalysisRun:
    run = db.get(AnalysisRun, run_id)
    if run is None or run.kind != AnalysisKind.PCB_OPTIMIZATION:
        raise not_found("Optimization run")
    try:
        access.get_project(db, user_id, run.project_id)
    except APIError as exc:
        if exc.status_code == 404:
            raise not_found("Optimization run") from exc
        raise
    return run


def get_candidate(
    db: Session, user_id: uuid.UUID, candidate_id: uuid.UUID, minimum: ProjectRole = ProjectRole.VIEWER
) -> OptimizationCandidate:
    cand = db.get(OptimizationCandidate, candidate_id)
    if cand is None:
        raise not_found("Candidate")
    try:
        project, _ = access.get_project(db, user_id, cand.project_id, minimum, action="decide on candidates")
    except APIError as exc:
        if exc.status_code == 404:
            raise not_found("Candidate") from exc
        raise
    if minimum != ProjectRole.VIEWER:
        access.ensure_active(project)
    return cand


def decide(
    db: Session, ctx: AuthContext, cand: OptimizationCandidate, status: str, reason: str | None, client: ClientInfo
) -> None:
    """Accept (only validated candidates) or reject a candidate. Accepting doesn't change the design."""
    if status == "accepted" and cand.status not in ("validated", "accepted"):
        raise APIError(
            409,
            "not_validated",
            "Only validated candidates can be accepted. Re-route and re-analyse first, or reject it.",
        )
    if status == "rejected" and not (reason or "").strip():
        raise APIError(422, "reason_required", "Say why you're rejecting this candidate.")
    cand.status, cand.status_reason = status, (reason or "").strip() or None
    cand.decided_by_id, cand.decided_at = ctx.user.id, utcnow()
    activity.record(db, CANDIDATE_DECIDED, actor_id=ctx.user.id, client=client, project_id=cand.project_id, target_type="optimization_candidate",
                    target_id=cand.id, details={"status": status, "candidate": cand.key})  # fmt: skip
