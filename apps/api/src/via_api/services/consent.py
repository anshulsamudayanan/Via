"""Explicit, scoped, revocable consent (docs/DATABASE.md "VIA Learn readiness").

No consent exists by default. A consent row is valid only while unrevoked and
recorded under the current policy version; changing what a scope means
requires a new ``POLICY_VERSION`` (old consents stop counting).
"""

from __future__ import annotations

import uuid

from sqlalchemy import select
from sqlalchemy.orm import Session

from via_api.models import DataConsent
from via_api.models.base import utcnow
from via_api.models.enums import ConsentScope
from via_api.services import activity
from via_api.services.activity import ClientInfo
from via_api.services.auth import AuthContext

#: Bump when the meaning of a scope changes; consents under older versions no longer count.
POLICY_VERSION = "2026-11-v1"

CONSENT_GRANTED = "consent.granted"
CONSENT_REVOKED = "consent.revoked"


def active_consent(db: Session, project_id: uuid.UUID, scope: ConsentScope) -> DataConsent | None:
    return db.scalar(
        select(DataConsent).where(
            DataConsent.project_id == project_id,
            DataConsent.scope == scope,
            DataConsent.revoked_at.is_(None),
            DataConsent.policy_version == POLICY_VERSION,
        )
    )


def grant(db: Session, ctx: AuthContext, project_id: uuid.UUID, scope: ConsentScope, client: ClientInfo) -> DataConsent:
    existing = active_consent(db, project_id, scope)
    if existing is not None:
        return existing
    consent = DataConsent(
        user_id=ctx.user.id, project_id=project_id, scope=scope, policy_version=POLICY_VERSION, granted_at=utcnow()
    )
    db.add(consent)
    db.flush()
    activity.record(
        db,
        CONSENT_GRANTED,
        actor_id=ctx.user.id,
        client=client,
        project_id=project_id,
        target_type="consent",
        target_id=consent.id,
        details={"scope": scope.value, "policy_version": POLICY_VERSION},
    )
    return consent


def revoke(db: Session, ctx: AuthContext, project_id: uuid.UUID, scope: ConsentScope, client: ClientInfo) -> bool:
    consent = active_consent(db, project_id, scope)
    if consent is None:
        return False
    consent.revoked_at = utcnow()
    activity.record(
        db,
        CONSENT_REVOKED,
        actor_id=ctx.user.id,
        client=client,
        project_id=project_id,
        target_type="consent",
        target_id=consent.id,
        details={"scope": scope.value},
    )
    return True
