"""/api/v1/ai: AI availability and per-project consent (no AI features yet)."""

from __future__ import annotations

import uuid
from typing import Annotated

from fastapi import APIRouter, Depends, status
from pydantic import BaseModel

from via_ai import AIProvider
from via_api.ai import ai_config, get_ai_provider
from via_api.deps import DB, AppSettings, Client, CurrentAuth
from via_api.errors import error_responses
from via_api.models.enums import ConsentScope, ProjectRole
from via_api.services import access, consent

router = APIRouter(prefix="/ai", tags=["ai"])


class AIStatus(BaseModel):
    enabled: bool
    provider: str
    text: bool
    structured_output: bool
    embeddings: bool
    #: Calls would leave VIA's infrastructure (project data needs consent).
    external: bool
    default_model: str | None


class ConsentStatus(BaseModel):
    scope: ConsentScope
    granted: bool
    policy_version: str
    granted_at: str | None = None


@router.get("/status", response_model=AIStatus, responses=error_responses(401))
def ai_status(
    settings: AppSettings, ctx: CurrentAuth, provider: Annotated[AIProvider, Depends(get_ai_provider)]
) -> AIStatus:
    caps = provider.capabilities
    return AIStatus(
        enabled=provider.name != "none",
        provider=provider.name,
        text=caps.text,
        structured_output=caps.structured_output,
        embeddings=caps.embeddings,
        external=caps.external,
        default_model=ai_config(settings).routing.default_model if provider.name != "none" else None,
    )


def _status(db: DB, project_id: uuid.UUID) -> ConsentStatus:
    row = consent.active_consent(db, project_id, ConsentScope.EXTERNAL_AI_PROCESSING)
    return ConsentStatus(
        scope=ConsentScope.EXTERNAL_AI_PROCESSING,
        granted=row is not None,
        policy_version=consent.POLICY_VERSION,
        granted_at=row.granted_at.isoformat() if row else None,
    )


@router.get("/consent/{project_id}", response_model=ConsentStatus, responses=error_responses(401, 404))
def get_consent(project_id: uuid.UUID, db: DB, ctx: CurrentAuth) -> ConsentStatus:
    """Whether this project allows sending its data to an external AI provider."""
    access.get_project(db, ctx.user.id, project_id)
    return _status(db, project_id)


@router.put("/consent/{project_id}", response_model=ConsentStatus, responses=error_responses(401, 403, 404))
def grant_consent(project_id: uuid.UUID, db: DB, client: Client, ctx: CurrentAuth) -> ConsentStatus:
    """Allow external AI processing of this project's parsed data (owner only). Revocable."""
    project, _ = access.get_project(db, ctx.user.id, project_id, ProjectRole.OWNER, action="manage AI consent")
    consent.grant(db, ctx, project.id, ConsentScope.EXTERNAL_AI_PROCESSING, client)
    db.commit()
    return _status(db, project_id)


@router.delete(
    "/consent/{project_id}", status_code=status.HTTP_204_NO_CONTENT, responses=error_responses(401, 403, 404)
)
def revoke_consent(project_id: uuid.UUID, db: DB, client: Client, ctx: CurrentAuth) -> None:
    project, _ = access.get_project(db, ctx.user.id, project_id, ProjectRole.OWNER, action="manage AI consent")
    consent.revoke(db, ctx, project.id, ConsentScope.EXTERNAL_AI_PROCESSING, client)
    db.commit()
