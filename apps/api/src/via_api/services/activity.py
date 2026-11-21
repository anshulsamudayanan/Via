"""Activity feed and security audit trail."""

from __future__ import annotations

import uuid
from dataclasses import dataclass
from typing import Any

from sqlalchemy.orm import Session

from via_api.models import ActivityLog


@dataclass(frozen=True)
class ClientInfo:
    ip_address: str | None = None
    user_agent: str | None = None


# Action names (stable identifiers shown in the activity feed and used in audits).
USER_REGISTERED = "user.registered"
LOGIN_SUCCEEDED = "auth.login_succeeded"
LOGIN_FAILED = "auth.login_failed"
LOGGED_OUT = "auth.logged_out"
SESSION_REVOKED = "auth.session_revoked"
PASSWORD_CHANGED = "auth.password_changed"  # noqa: S105 - action name
PASSWORD_RESET_REQUESTED = "auth.password_reset_requested"  # noqa: S105 - action name
PASSWORD_RESET_COMPLETED = "auth.password_reset_completed"  # noqa: S105 - action name
PROFILE_UPDATED = "user.profile_updated"
ORGANIZATION_CREATED = "organization.created"
PROJECT_CREATED = "project.created"
PROJECT_UPDATED = "project.updated"
PROJECT_ARCHIVED = "project.archived"
PROJECT_UNARCHIVED = "project.unarchived"
PROJECT_DELETED = "project.deleted"
PROJECT_MEMBER_ADDED = "project.member_added"
PROJECT_MEMBER_UPDATED = "project.member_updated"
PROJECT_MEMBER_REMOVED = "project.member_removed"

#: Never stored in ``details`` even if a caller passes them by mistake.
_FORBIDDEN_DETAIL_KEYS = {"password", "new_password", "current_password", "token", "session_token", "password_hash"}


def record(
    db: Session,
    action: str,
    *,
    actor_id: uuid.UUID | None,
    client: ClientInfo | None = None,
    project_id: uuid.UUID | None = None,
    organization_id: uuid.UUID | None = None,
    target_type: str | None = None,
    target_id: uuid.UUID | None = None,
    details: dict[str, Any] | None = None,
) -> ActivityLog:
    safe = {k: v for k, v in (details or {}).items() if k not in _FORBIDDEN_DETAIL_KEYS}
    entry = ActivityLog(
        actor_id=actor_id,
        action=action,
        project_id=project_id,
        organization_id=organization_id,
        target_type=target_type,
        target_id=target_id,
        ip_address=client.ip_address if client else None,
        user_agent=(client.user_agent or "")[:512] or None if client else None,
        details=safe,
    )
    db.add(entry)
    return entry
