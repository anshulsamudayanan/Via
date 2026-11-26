# ruff: noqa: E501
"""Change management: change sets, export by patching the original file, lineage and rollback.

A change set collects explicit changes (from accepted optimization candidates or entered by the user)
against one parsed base revision. Applying it runs a ``pcb_export`` job: the worker patches the
original upload in the sandbox (``via_opt.cli``), which verifies the patch by re-parsing, stores the
result as a new revision with ``parent_revision_id = base`` and imports it through the normal pipeline.
Nothing is ever overwritten or deleted: rollback only makes the base revision current again.
"""

from __future__ import annotations

import hashlib
import io
import logging
import os
import uuid
from collections.abc import Callable
from typing import Any

from pydantic import ValidationError
from sqlalchemy import delete, select
from sqlalchemy.orm import Session
from via_opt import EXPORTABLE, Change, ChangeKind, apply, metrics

from via_api.errors import APIError, not_found
from via_api.models import (
    AnalysisFinding,
    AnalysisRun,
    ChangeSet,
    Design,
    DesignChange,
    DesignFile,
    DesignRevision,
    OptimizationCandidate,
)
from via_api.models.base import utcnow
from via_api.models.enums import (
    AnalysisKind,
    AnalysisStatus,
    ChangeSetStatus,
    ChangeStatus,
    DesignFileKind,
    ProjectRole,
    RevisionStatus,
)
from via_api.parsing.importer import source_file
from via_api.parsing.sandbox import ExportOutcome, SandboxLimits, run_exporter
from via_api.services import access, activity
from via_api.services import designs as design_svc
from via_api.services.activity import ClientInfo
from via_api.services.analysis import _load_design, analysis_job_id, fail_run
from via_api.services.auth import AuthContext
from via_api.storage import StorageBackend, StorageError, revision_object_key
from via_pcb import PCBDesign

logger = logging.getLogger("via_api.changes")

CHANGE_SET_CREATED = "change_set.created"
CHANGE_SET_APPLY_REQUESTED = "change_set.apply_requested"
CHANGE_SET_APPLIED = "change_set.applied"
CHANGE_SET_FAILED = "change_set.failed"
CHANGE_SET_ROLLED_BACK = "change_set.rolled_back"
CHANGE_SET_DISCARDED = "change_set.discarded"
MAX_CHANGES = 2000


def export_job_id(run_id: uuid.UUID | str, attempt: int) -> str:
    return f"export-{run_id}-a{attempt}"


# --------------------------------------------------------------------------- access


def get_change_set(
    db: Session, user_id: uuid.UUID, change_set_id: uuid.UUID, minimum: ProjectRole = ProjectRole.VIEWER
) -> ChangeSet:
    cs = db.get(ChangeSet, change_set_id)
    if cs is None:
        raise not_found("Change set")
    try:
        project, _ = access.get_project(db, user_id, cs.project_id, minimum, action="change designs")
    except APIError as exc:
        if exc.status_code == 404:
            raise not_found("Change set") from exc
        raise
    if minimum != ProjectRole.VIEWER:
        access.ensure_active(project)
    return cs


def changes_of(db: Session, cs: ChangeSet) -> list[DesignChange]:
    return list(
        db.scalars(select(DesignChange).where(DesignChange.change_set_id == cs.id).order_by(DesignChange.ordinal)).all()
    )


def _as_change(row: DesignChange) -> Change:
    return Change.model_validate({"kind": row.kind, "target": row.target, "before": row.before, "after": row.after,
                                  "reason": row.reason, "source": row.source, "finding_ids": list(row.finding_ids or [])})  # fmt: skip


# --------------------------------------------------------------------------- creation


def _before(design: PCBDesign, ch: Change) -> dict[str, Any]:
    """The current value of what ``ch`` changes, read from the design (never trusted from the client)."""
    tid = ch.target.id
    if ch.kind in (ChangeKind.MOVE_COMPONENT, ChangeKind.ROTATE_COMPONENT):
        c = next((c for c in design.components if c.id == tid), None)
        if c is None:
            raise LookupError(f"component {ch.target.label or tid} isn't in this revision")
        return (
            {"x": c.position.x, "y": c.position.y} if ch.kind == ChangeKind.MOVE_COMPONENT else {"rotation": c.rotation}
        )
    if ch.kind == ChangeKind.SET_TRACK_WIDTH:
        t = next((t for t in design.tracks if t.id == tid), None)
        if t is None:
            raise LookupError(f"track {tid} isn't in this revision")
        return {"width": t.width}
    if ch.kind in (ChangeKind.MOVE_VIA, ChangeKind.SET_VIA_SIZE):
        v = next((v for v in design.vias if v.id == tid), None)
        if v is None:
            raise LookupError(f"via {tid} isn't in this revision")
        return (
            {"x": v.position.x, "y": v.position.y}
            if ch.kind == ChangeKind.MOVE_VIA
            else {"diameter": v.diameter, "drill": v.drill}
        )
    if ch.kind == ChangeKind.SET_OUTLINE_RECT:
        bb = design.outline.bbox
        return bb.model_dump() if bb else {}
    raise LookupError(f"{ch.kind.value} can't be exported automatically")


def _validate_after(ch: Change) -> None:
    a = ch.after
    try:
        if ch.kind in (ChangeKind.MOVE_COMPONENT, ChangeKind.MOVE_VIA):
            float(a["x"]), float(a["y"])
        elif ch.kind == ChangeKind.ROTATE_COMPONENT:
            float(a["rotation"])
        elif ch.kind == ChangeKind.SET_TRACK_WIDTH:
            if not 0 < float(a["width"]) <= 50:
                raise ValueError("width must be between 0 and 50 mm")
        elif ch.kind == ChangeKind.SET_VIA_SIZE:
            d, h = float(a["diameter"]), float(a["drill"])
            if not 0 < h < d <= 20:
                raise ValueError("a via needs 0 < drill < diameter <= 20 mm")
        elif ch.kind == ChangeKind.SET_OUTLINE_RECT:
            x1, y1, x2, y2 = (float(a[k]) for k in ("min_x", "min_y", "max_x", "max_y"))
            if not (x2 > x1 and y2 > y1):
                raise ValueError("the outline needs max > min")
    except (KeyError, TypeError, ValueError) as exc:
        raise APIError(422, "invalid_change", f"{ch.kind.value}: {exc}") from None


def create(
    db: Session,
    storage: StorageBackend,
    ctx: AuthContext,
    design_id: uuid.UUID,
    *,
    title: str | None,
    candidate_ids: list[uuid.UUID],
    user_changes: list[dict[str, Any]],
    client: ClientInfo,
) -> ChangeSet:
    design, project, _ = design_svc.get_design(db, ctx.user.id, design_id, ProjectRole.EDITOR, action="change designs")
    access.ensure_active(project)
    revision = design_svc.resolve_parsed_revision(db, design, None)
    collected: list[tuple[Change, uuid.UUID | None]] = []
    for cid in dict.fromkeys(candidate_ids):
        cand = db.get(OptimizationCandidate, cid)
        if cand is None or cand.design_id != design.id:
            raise not_found("Candidate")
        if cand.status != "accepted":
            raise APIError(409, "candidate_not_accepted", f'Candidate "{cand.title}" isn\'t accepted.')
        if cand.revision_id != revision.id:
            raise APIError(
                409,
                "candidate_outdated",
                f'Candidate "{cand.title}" was made for an older revision. Re-run the optimization.',
            )
        rows = db.scalars(
            select(DesignChange).where(DesignChange.candidate_id == cand.id).order_by(DesignChange.ordinal)
        ).all()
        if any(not r.exportable for r in rows):
            raise APIError(
                409,
                "not_exportable",
                f'Candidate "{cand.title}" includes changes VIA can\'t write into the file; make them in your EDA tool.',
            )
        collected += [(_as_change(r), cand.id) for r in rows]
    for raw in user_changes:
        try:
            ch = Change.model_validate(
                {
                    **raw,
                    "before": raw.get("before") or {},
                    "source": "user",
                    "reason": raw.get("reason") or "Entered by user",
                }
            )
        except ValidationError as exc:
            raise APIError(
                422,
                "invalid_change",
                "A change isn't valid.",
                {"errors": exc.errors(include_url=False, include_context=False)},
            ) from None
        if ch.kind not in EXPORTABLE:
            raise APIError(422, "not_exportable", f"{ch.kind.value} can't be written into the file automatically.")
        collected.append((ch, None))
    if not collected:
        raise APIError(422, "empty_change_set", "Choose at least one accepted candidate or change.")
    if len(collected) > MAX_CHANGES:
        raise APIError(422, "too_many_changes", f"A change set can hold at most {MAX_CHANGES} changes.")
    seen: dict[str, int] = {}
    for i, (ch, _) in enumerate(collected):
        key = f"{ch.target.kind}:{ch.target.id}"
        if key in seen:
            raise APIError(409, "conflicting_changes", f"Two changes target the same object ({ch.target.label or ch.target.id}).",
                           {"target": ch.target.model_dump(), "changes": [seen[key], i]})  # fmt: skip
        seen[key] = i
        _validate_after(ch)
    design_model = _load_design(db, storage, revision)
    try:
        befores = [_before(design_model, ch) for ch, _ in collected]
        apply(design_model, [ch for ch, _ in collected])
    except (LookupError, ValueError) as exc:
        raise APIError(422, "invalid_change", str(exc)) from None
    cs = ChangeSet(project_id=project.id, design_id=design.id, base_revision_id=revision.id, created_by_id=ctx.user.id,
                   title=(title or "").strip()[:200] or f"Changes to revision {revision.revision_number}")  # fmt: skip
    db.add(cs)
    db.flush()
    for i, ((ch, origin), before) in enumerate(zip(collected, befores, strict=True)):
        db.add(DesignChange(change_set_id=cs.id, origin_candidate_id=origin, project_id=project.id, design_id=design.id,
                            revision_id=revision.id, ordinal=i, kind=ch.kind.value, target=ch.target.model_dump(), before=before,
                            after=ch.after, reason=ch.reason, source=ch.source, finding_ids=ch.finding_ids, exportable=True))  # fmt: skip
    activity.record(db, CHANGE_SET_CREATED, actor_id=ctx.user.id, client=client, project_id=project.id, target_type="change_set",
                    target_id=cs.id, details={"changes": len(collected), "revision": revision.revision_number})  # fmt: skip
    return cs


def preview(db: Session, storage: StorageBackend, cs: ChangeSet) -> dict[str, Any]:
    """Metrics of the base revision and of the model with the changes applied (a simulation, not the export)."""
    base = db.get(DesignRevision, cs.base_revision_id)
    assert base is not None
    design = _load_design(db, storage, base)
    after = apply(design, [_as_change(r) for r in changes_of(db, cs)])
    before_m, after_m = metrics(design), metrics(after)
    deltas: dict[str, float | None] = {}
    for k, v in before_m.items():
        a = after_m.get(k)
        deltas[k] = round(a - v, 6) if a is not None and v is not None else None
    return {"source": "simulated", "before": before_m, "after": after_m, "deltas": deltas}


def remove_change(db: Session, cs: ChangeSet, change_id: uuid.UUID) -> None:
    _require_draft(cs)
    row = db.get(DesignChange, change_id)
    if row is None or row.change_set_id != cs.id:
        raise not_found("Change")
    db.delete(row)


def discard(db: Session, ctx: AuthContext, cs: ChangeSet, client: ClientInfo) -> None:
    _require_draft(cs)
    activity.record(db, CHANGE_SET_DISCARDED, actor_id=ctx.user.id, client=client, project_id=cs.project_id,
                    target_type="change_set", target_id=cs.id, details={"title": cs.title})  # fmt: skip
    db.execute(delete(DesignChange).where(DesignChange.change_set_id == cs.id))
    db.delete(cs)


def _require_draft(cs: ChangeSet) -> None:
    if cs.status not in (ChangeSetStatus.DRAFT, ChangeSetStatus.FAILED):
        raise APIError(409, "change_set_locked", "This change set has been applied; roll it back or start a new one.")


# --------------------------------------------------------------------------- apply (API side)


def request_apply(db: Session, ctx: AuthContext, cs: ChangeSet, client: ClientInfo) -> AnalysisRun:
    # Lock the design, then the change set: concurrent applies serialize here.
    design = db.scalar(select(Design).where(Design.id == cs.design_id).with_for_update())
    db.refresh(cs, with_for_update=True)
    _require_draft(cs)
    busy = db.scalar(
        select(ChangeSet.id).where(ChangeSet.design_id == cs.design_id, ChangeSet.status == ChangeSetStatus.APPLYING)
    )
    if busy is not None:
        raise APIError(
            409, "apply_in_progress", "Another change set is being applied to this design. Wait for it to finish."
        )
    if design is None or design.current_revision_id != cs.base_revision_id:
        raise APIError(
            409,
            "base_not_current",
            "The design has a newer revision than this change set's base. Create a new change set.",
        )
    if not changes_of(db, cs):
        raise APIError(422, "empty_change_set", "This change set has no changes left.")
    run = AnalysisRun(project_id=cs.project_id, revision_id=cs.base_revision_id, kind=AnalysisKind.PCB_EXPORT, status=AnalysisStatus.QUEUED,
                      config={"change_set_id": str(cs.id)}, attempt=1, triggered_by_id=ctx.user.id)  # fmt: skip
    db.add(run)
    db.flush()
    run.job_id = export_job_id(run.id, 1)
    cs.status, cs.export_run_id, cs.applied_by_id = ChangeSetStatus.APPLYING, run.id, ctx.user.id
    cs.error_code = cs.error_message = None
    activity.record(db, CHANGE_SET_APPLY_REQUESTED, actor_id=ctx.user.id, client=client, project_id=cs.project_id,
                    target_type="change_set", target_id=cs.id, details={"title": cs.title})  # fmt: skip
    return run


def fail_change_set(db: Session, cs: ChangeSet, run: AnalysisRun | None, code: str, message: str) -> None:
    cs.status, cs.error_code, cs.error_message = ChangeSetStatus.FAILED, code, message
    if run is not None and run.status != AnalysisStatus.FAILED:
        fail_run(db, run, code, message)
    activity.record(db, CHANGE_SET_FAILED, actor_id=cs.applied_by_id, project_id=cs.project_id, target_type="change_set",
                    target_id=cs.id, details={"code": code})  # fmt: skip


# --------------------------------------------------------------------------- apply (worker side)


def _export_filename(original: str | None, number: int) -> str:
    base, ext = os.path.splitext(original or "board.kicad_pcb")
    return f"{base[:180]}-via-r{number}{ext or '.kicad_pcb'}"


def process_export(
    db: Session,
    storage: StorageBackend,
    run_id: uuid.UUID,
    limits: SandboxLimits,
    *,
    import_revision: Callable[[uuid.UUID], DesignRevision | None],
    export: Callable[..., ExportOutcome] = run_exporter,
    attempt: int = 1,
    job_id: str | None = None,
) -> AnalysisRun | None:
    run = db.get(AnalysisRun, run_id)
    if run is None or run.kind != AnalysisKind.PCB_EXPORT:
        return None
    cs = db.get(ChangeSet, uuid.UUID(run.config["change_set_id"]))
    if cs is None or run.status == AnalysisStatus.SUCCEEDED:
        return run
    run.status, run.started_at, run.heartbeat_at = AnalysisStatus.RUNNING, utcnow(), utcnow()
    run.attempt, run.job_id = attempt, job_id or run.job_id
    run.error_code = run.error_message = None
    db.commit()
    base = db.get(DesignRevision, cs.base_revision_id)
    src = source_file(db, base) if base else None
    if base is None or src is None:
        fail_change_set(db, cs, run, "base_unavailable", "The base revision's file is missing.")
        db.commit()
        return run
    # A retry after a crash may find the result already imported.
    if cs.result_revision_id is not None:
        done = db.get(DesignRevision, cs.result_revision_id)
        if done is not None and done.status == RevisionStatus.READY:
            _finish(db, cs, run, done)
            db.commit()
            return run
    rows = changes_of(db, cs)
    try:
        data = storage.get(src.storage_key)
    except (StorageError, OSError):
        fail_change_set(db, cs, run, "storage_unavailable", "The original file couldn't be read. Try again shortly.")
        db.commit()
        return run
    outcome = export(data, src.original_filename, [_as_change(r).model_dump(mode="json") for r in rows], limits)
    if outcome.data is None:
        fail_change_set(
            db, cs, run, outcome.error_code or "export_failed", outcome.error_message or "The export failed."
        )
        db.commit()
        return run
    refused = dict(outcome.refused)
    for i, r in enumerate(rows):
        r.status = ChangeStatus.REFUSED if i in refused else ChangeStatus.PROPOSED
        r.status_reason = refused.get(i)
    if refused:
        # A change set is applied as a whole or not at all: a partial export would misrepresent it.
        fail_change_set(
            db,
            cs,
            run,
            "changes_refused",
            f"{len(refused)} change(s) couldn't be written into the file; remove them and apply again.",
        )
        db.commit()
        return run
    sha = hashlib.sha256(outcome.data).hexdigest()
    number = design_svc.next_revision_number(db, cs.design_id)  # locks the design row
    current = db.scalar(select(Design.current_revision_id).where(Design.id == cs.design_id))
    if current != base.id:
        fail_change_set(
            db,
            cs,
            run,
            "base_not_current",
            "The design changed while this change set was being applied. Create a new change set.",
        )
        db.commit()
        return run
    rev = DesignRevision(design_id=cs.design_id, project_id=cs.project_id, revision_number=number, status=RevisionStatus.PENDING,
                         source_format=base.source_format, source_sha256=sha, created_by_id=cs.applied_by_id, parent_revision_id=base.id)  # fmt: skip
    db.add(rev)
    db.flush()
    key = revision_object_key(cs.project_id, rev.id, "source")
    try:
        storage.put(key, io.BytesIO(outcome.data), content_type="application/octet-stream", size=len(outcome.data))
    except StorageError:
        db.rollback()
        fail_change_set(db, cs, run, "storage_unavailable", "The exported file couldn't be stored. Try again shortly.")
        db.commit()
        return run
    db.add(DesignFile(revision_id=rev.id, project_id=cs.project_id, kind=DesignFileKind.SOURCE, storage_key=key,
                      original_filename=_export_filename(src.original_filename, number), content_type=src.content_type,
                      size_bytes=len(outcome.data), sha256=sha))  # fmt: skip
    cs.result_revision_id = rev.id
    cs.result = {"applied": len(outcome.applied), "board_member": outcome.board_member, "sha256": sha, "size_bytes": len(outcome.data),
                 "verification": "re-parsed; every changed object matches its change and every other object is unchanged"}  # fmt: skip
    db.commit()
    imported = import_revision(rev.id)
    db.refresh(cs)
    if imported is None or imported.status != RevisionStatus.READY:
        fail_change_set(
            db,
            cs,
            run,
            "import_failed",
            (imported.error_message if imported else None) or "The exported file couldn't be imported.",
        )
        db.commit()
        return run
    _finish(db, cs, run, imported)
    db.commit()
    return run


def _finish(db: Session, cs: ChangeSet, run: AnalysisRun, rev: DesignRevision) -> None:
    for r in changes_of(db, cs):
        r.status, r.status_reason = ChangeStatus.APPLIED, None
    now = utcnow()
    cs.status, cs.applied_at = ChangeSetStatus.APPLIED, now
    design = db.get(Design, cs.design_id)
    if design is not None:
        design.current_revision_id = rev.id
    _follow_up_analysis(db, cs, rev)
    run.status, run.finished_at = AnalysisStatus.SUCCEEDED, now
    run.result_summary = {"change_set_id": str(cs.id), "result_revision_id": str(rev.id), **cs.result}
    activity.record(db, CHANGE_SET_APPLIED, actor_id=cs.applied_by_id, project_id=cs.project_id, target_type="change_set",
                    target_id=cs.id, details={"revision": rev.revision_number, "changes": cs.result.get("applied")})  # fmt: skip


def _follow_up_analysis(db: Session, cs: ChangeSet, rev: DesignRevision) -> None:
    """Queue the same analysis on the new revision that last ran on the base, so findings can be compared."""
    last = db.scalar(select(AnalysisRun).where(AnalysisRun.revision_id == cs.base_revision_id, AnalysisRun.kind == AnalysisKind.PCB_ANALYSIS,
                                               AnalysisRun.status == AnalysisStatus.SUCCEEDED).order_by(AnalysisRun.created_at.desc()))  # fmt: skip
    if last is None:
        return
    run = AnalysisRun(project_id=cs.project_id, revision_id=rev.id, kind=AnalysisKind.PCB_ANALYSIS, status=AnalysisStatus.QUEUED,
                      config=last.config, attempt=1, triggered_by_id=cs.applied_by_id)  # fmt: skip
    db.add(run)
    db.flush()
    run.job_id = analysis_job_id(run.id, 1)
    cs.result = {**cs.result, "follow_up_analysis_run_id": str(run.id)}


# --------------------------------------------------------------------------- rollback & history


def rollback(db: Session, ctx: AuthContext, cs: ChangeSet, client: ClientInfo) -> None:
    design = db.scalar(select(Design).where(Design.id == cs.design_id).with_for_update())
    db.refresh(cs, with_for_update=True)
    if cs.status != ChangeSetStatus.APPLIED:
        raise APIError(409, "not_applied", "Only an applied change set can be rolled back.")
    if design is None or design.current_revision_id != cs.result_revision_id:
        raise APIError(409, "not_current", "A newer revision is current; roll that back first.")
    design.current_revision_id = cs.base_revision_id
    cs.status, cs.rolled_back_by_id, cs.rolled_back_at = ChangeSetStatus.ROLLED_BACK, ctx.user.id, utcnow()
    activity.record(db, CHANGE_SET_ROLLED_BACK, actor_id=ctx.user.id, client=client, project_id=cs.project_id,
                    target_type="change_set", target_id=cs.id, details={"title": cs.title})  # fmt: skip


def _latest_findings(db: Session, revision_id: uuid.UUID) -> tuple[AnalysisRun | None, list[AnalysisFinding]]:
    run = db.scalar(select(AnalysisRun).where(AnalysisRun.revision_id == revision_id, AnalysisRun.kind == AnalysisKind.PCB_ANALYSIS,
                                              AnalysisRun.status == AnalysisStatus.SUCCEEDED).order_by(AnalysisRun.created_at.desc()))  # fmt: skip
    if run is None:
        return None, []
    return run, list(db.scalars(select(AnalysisFinding).where(AnalysisFinding.run_id == run.id)).all())


def compare_revisions(db: Session, base: DesignRevision, head: DesignRevision) -> dict[str, Any]:
    """Object counts and findings (matched by fingerprint) of two revisions of one design."""
    base_run, base_f = _latest_findings(db, base.id)
    head_run, head_f = _latest_findings(db, head.id)
    counts = {k: {"base": base.object_counts.get(k), "head": head.object_counts.get(k)}
              for k in sorted(set(base.object_counts) | set(head.object_counts))}  # fmt: skip
    out: dict[str, Any] = {
        "base": {"revision_id": str(base.id), "revision_number": base.revision_number, "analysis_run_id": str(base_run.id) if base_run else None},
        "head": {"revision_id": str(head.id), "revision_number": head.revision_number, "analysis_run_id": str(head_run.id) if head_run else None},
        "object_counts": counts,
        "findings": None,
    }  # fmt: skip
    if base_run is None or head_run is None:
        return out
    if base_run.config.get("checks") != head_run.config.get("checks"):
        out["findings_note"] = "The two analyses ran different checks, so some differences may come from that."
    by_b = {f.fingerprint: f for f in base_f}
    by_h = {f.fingerprint: f for f in head_f}

    def brief(f: AnalysisFinding) -> dict[str, Any]:
        return {
            "id": str(f.id),
            "rule": f.rule,
            "severity": f.severity.value,
            "title": f.title,
            "source": f.source.value,
        }

    out["findings"] = {
        "introduced": [brief(by_h[k]) for k in by_h.keys() - by_b.keys()][:500],
        "resolved": [brief(by_b[k]) for k in by_b.keys() - by_h.keys()][:500],
        "persisting": len(by_b.keys() & by_h.keys()),
        "base_total": len(base_f),
        "head_total": len(head_f),
    }
    return out


def lineage(db: Session, design_id: uuid.UUID) -> list[dict[str, Any]]:
    revs = db.scalars(
        select(DesignRevision).where(DesignRevision.design_id == design_id).order_by(DesignRevision.revision_number)
    ).all()
    sets = {
        cs.result_revision_id: cs
        for cs in db.scalars(
            select(ChangeSet).where(ChangeSet.design_id == design_id, ChangeSet.result_revision_id.is_not(None))
        )
    }
    return [{"revision_id": str(r.id), "revision_number": r.revision_number, "status": r.status.value,
             "parent_revision_id": str(r.parent_revision_id) if r.parent_revision_id else None,
             "change_set_id": str(sets[r.id].id) if r.id in sets else None, "created_at": r.created_at.isoformat()} for r in revs]  # fmt: skip
