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
    MAX_NETS,
    ContextComponent,
    ContextLayer,
    ContextPurpose,
    ProjectContext,
)
from via_api.errors import APIError
from via_api.models import PCBComponent, PCBLayer, PCBNet
from via_api.models.enums import ConsentScope
from via_api.services import designs
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
        self, *, user_id: uuid.UUID, design_id: uuid.UUID, purpose: ContextPurpose, external: bool
    ) -> ProjectContext:
        db = self.db
        design, project, _ = designs.get_design(db, user_id, design_id)
        if external and active_consent(db, project.id, ConsentScope.EXTERNAL_AI_PROCESSING) is None:
            raise ConsentRequiredError()
        revision = designs.resolve_parsed_revision(db, design, None)

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
            truncated=truncated,
        )
