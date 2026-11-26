# ruff: noqa: E501
"""Database-backed ContextProvider: the gate between project data and any model.

Checks, in order: the caller can view the design's project (404 otherwise, like
every project-scoped read); for external providers, the project has an active
``external_ai_processing`` consent (403 ``consent_required`` otherwise); the
design has a parsed revision. Then builds a small summary from database rows
only: no object-storage reads, no source files, no normalized geometry.
"""

from __future__ import annotations

import uuid

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from via_ai.context import (
    MAX_COMPONENTS,
    MAX_FINDINGS,
    MAX_NETS,
    ContextComponent,
    ContextComponentRecord,
    ContextFinding,
    ContextFocus,
    ContextLayer,
    ContextPurpose,
    ProjectContext,
)
from via_api.errors import APIError
from via_api.models import (
    AnalysisFinding,
    AnalysisRun,
    ComponentRecord,
    DesignRevision,
    FindingEvidence,
    PCBComponent,
    PCBLayer,
    PCBNet,
)
from via_api.models.enums import AnalysisKind, AnalysisStatus, ConsentScope
from via_api.services import components, designs
from via_api.services.consent import active_consent


class ConsentRequiredError(APIError):
    def __init__(self) -> None:
        super().__init__(
            403,
            "consent_required",
            "The project owner hasn't allowed sending this project's data to an external AI provider.",
        )


class DatabaseContextProvider:
    def __init__(self, db: Session) -> None:
        self.db = db

    def build(
        self,
        *,
        user_id: uuid.UUID,
        design_id: uuid.UUID,
        purpose: ContextPurpose,
        external: bool,
        focus: tuple[str, str] | None = None,
        run_id: uuid.UUID | None = None,
    ) -> ProjectContext:
        db = self.db
        design, project, _ = designs.get_design(db, user_id, design_id)
        if external and active_consent(db, project.id, ConsentScope.EXTERNAL_AI_PROCESSING) is None:
            raise ConsentRequiredError()
        revision = designs.resolve_parsed_revision(db, design, None)
        run = self._run(revision.id, run_id)
        findings = self._findings(run)
        context_focus = self._focus(revision.id, run, focus) if focus else None

        layers = db.scalars(select(PCBLayer).where(PCBLayer.revision_id == revision.id).order_by(PCBLayer.ordinal))
        net_total = db.scalar(select(func.count(PCBNet.id)).where(PCBNet.revision_id == revision.id)) or 0
        nets = db.scalars(
            select(PCBNet.name)
            .where(PCBNet.revision_id == revision.id)
            .order_by(func.lower(PCBNet.name))
            .limit(MAX_NETS)
        )
        comp_total = db.scalar(select(func.count(PCBComponent.id)).where(PCBComponent.revision_id == revision.id)) or 0
        comps = db.scalars(
            select(PCBComponent)
            .where(PCBComponent.revision_id == revision.id)
            .order_by(PCBComponent.reference)
            .limit(MAX_COMPONENTS)
        )
        truncated = {
            k: v
            for k, v in {"net_names": net_total - MAX_NETS, "components": comp_total - MAX_COMPONENTS}.items()
            if v > 0
        }
        return ProjectContext(
            purpose=purpose,
            project_id=project.id,
            design_id=design.id,
            revision_id=revision.id,
            revision_number=revision.revision_number,
            design_name=design.name,
            source_format=revision.source_format,
            stats={k: v for k, v in revision.object_counts.items() if isinstance(v, int | float) or v is None},
            layers=[ContextLayer(name=layer.name, kind=layer.kind, side=layer.side) for layer in layers],
            net_names=list(nets),
            components=[
                ContextComponent(reference=c.reference, value=c.value, footprint=c.footprint, side=c.side)
                for c in comps
            ],
            warnings=[f"{w.get('code')}: {w.get('message')}" for w in revision.warnings],
            truncated={
                **truncated,
                **(
                    {"findings": run_total - MAX_FINDINGS}
                    if run and (run_total := self._count(run)) > MAX_FINDINGS
                    else {}
                ),
            },
            analysis_run_id=run.id if run else None,
            findings=findings,
            focus=context_focus,
            design_rules=self._rules(revision),
            component_records=self._records(project.id, revision.id),
        )

    # --- Stage 2 additions ------------------------------------------------------------------

    def _run(self, revision_id: uuid.UUID, run_id: uuid.UUID | None) -> AnalysisRun | None:
        stmt = select(AnalysisRun).where(
            AnalysisRun.revision_id == revision_id,
            AnalysisRun.kind == AnalysisKind.PCB_ANALYSIS,
            AnalysisRun.status == AnalysisStatus.SUCCEEDED,
        )
        if run_id is not None:
            run = self.db.scalar(stmt.where(AnalysisRun.id == run_id))
            if run is None:
                raise APIError(404, "not_found", "Analysis run not found for this design's current revision.")
            return run
        return self.db.scalar(stmt.order_by(AnalysisRun.created_at.desc()))

    def _count(self, run: AnalysisRun) -> int:
        return self.db.scalar(select(func.count(AnalysisFinding.id)).where(AnalysisFinding.run_id == run.id)) or 0

    def _findings(self, run: AnalysisRun | None) -> list[ContextFinding]:
        if run is None:
            return []
        rows = self.db.scalars(
            select(AnalysisFinding)
            .where(AnalysisFinding.run_id == run.id)
            .order_by(AnalysisFinding.severity_rank, AnalysisFinding.title)
            .limit(MAX_FINDINGS)
        ).all()
        evidence: dict[uuid.UUID, list[str]] = {}
        if rows:
            for e in self.db.scalars(
                select(FindingEvidence)
                .where(FindingEvidence.finding_id.in_([r.id for r in rows]))
                .order_by(FindingEvidence.ordinal)
            ):
                evidence.setdefault(e.finding_id, []).append(f"{e.label}: {e.value}"[:300])
        return [
            ContextFinding(
                id=str(r.id),
                check_id=r.check_id,
                rule=r.rule,
                severity=r.severity.value,
                source=r.source.value,
                verification=r.verification.value,
                title=r.title,
                description=r.description[:1000],
                components=list(r.components)[:50],
                nets=list(r.nets)[:50],
                evidence=evidence.get(r.id, [])[:12],
            )
            for r in rows
        ]

    def _focus(self, revision_id: uuid.UUID, run: AnalysisRun | None, focus: tuple[str, str]) -> ContextFocus:
        kind, oid = focus
        db = self.db
        if kind == "finding":
            f = db.get(AnalysisFinding, uuid.UUID(oid)) if _is_uuid(oid) else None
            if f is None or f.revision_id != revision_id:
                raise APIError(404, "not_found", "Finding not found for this design's current revision.")
            return ContextFocus(kind="finding", id=oid, details={
                "title": f.title, "explanation": f.explanation, "suggested_resolution": f.suggested_resolution,
                "source": f.source.value, "verification": f.verification.value,
            })  # fmt: skip
        if kind == "component":
            c = db.scalar(
                select(PCBComponent).where(PCBComponent.revision_id == revision_id, PCBComponent.reference == oid)
            )
            if c is None:
                raise APIError(404, "not_found", f"Component {oid[:50]} isn't in this design.")
            return ContextFocus(kind="component", id=oid, details={
                "value": c.value, "footprint": c.footprint, "side": c.side, "x_mm": c.x, "y_mm": c.y,
                "rotation_deg": c.rotation, "pads": c.pad_count,
                "properties": [f"{k}: {v}" for k, v in sorted((c.properties or {}).items())][:20],
            })  # fmt: skip
        if kind == "net":
            n = db.scalar(select(PCBNet).where(PCBNet.revision_id == revision_id, PCBNet.name == oid))
            if n is None:
                raise APIError(404, "not_found", f"Net {oid[:50]} isn't in this design.")
            return ContextFocus(kind="net", id=oid, details={
                "pads": n.pad_count, "tracks": n.track_count, "vias": n.via_count, "track_length_mm": round(n.track_length, 3),
            })  # fmt: skip
        if kind == "region":
            try:
                x1, y1, x2, y2 = (float(v) for v in oid.split(","))
            except ValueError:
                raise APIError(422, "invalid_focus", "A region is 'min_x,min_y,max_x,max_y' in mm.") from None
            inside = db.scalars(select(PCBComponent.reference).where(
                PCBComponent.revision_id == revision_id, PCBComponent.x.between(min(x1, x2), max(x1, x2)),
                PCBComponent.y.between(min(y1, y2), max(y1, y2)))).all()  # fmt: skip
            return ContextFocus(kind="region", id=oid, details={"components_inside": sorted(inside)[:100]})
        raise APIError(422, "invalid_focus", "Focus kind must be finding, component, net or region.")

    def _rules(self, revision: DesignRevision) -> dict[str, float | bool | str | None]:
        constraints = (revision.summary or {}).get("constraints", {})
        rules = constraints.get("rules") or {}
        out: dict[str, float | bool | str | None] = {"rules_source": constraints.get("rules_source", "board_file")}
        out.update({k: v for k, v in rules.items() if v is not None and isinstance(v, int | float | bool)})
        return out

    def _records(self, project_id: uuid.UUID, revision_id: uuid.UUID) -> list[ContextComponentRecord]:
        comps = self.db.scalars(select(PCBComponent).where(PCBComponent.revision_id == revision_id)).all()
        refs: dict[uuid.UUID, list[str]] = {}
        records: dict[uuid.UUID, ComponentRecord] = {}
        for c, _, _, record in components.matches(self.db, project_id, list(comps)):
            if record is not None:
                refs.setdefault(record.id, []).append(c.reference)
                records[record.id] = record
        return [
            ContextComponentRecord(
                references=sorted(refs[r.id])[:50],
                manufacturer=r.manufacturer,
                part_number=r.part_number,
                description=r.description,
                package=r.package,
                verification=r.verification,
                specs=[
                    f"{s.get('name')}: {s.get('value')} {s.get('unit') or ''} ({s.get('source')}, "
                    f"{'verified' if s.get('verified') else 'unverified'})".replace("  ", " ")
                    for s in r.specs
                ][:40],
            )
            for r in list(records.values())[:100]
        ]


def _is_uuid(value: str) -> bool:
    try:
        uuid.UUID(value)
    except ValueError:
        return False
    return True
