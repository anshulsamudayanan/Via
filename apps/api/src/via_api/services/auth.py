"""Registration, login, sessions and password management."""

from __future__ import annotations

import uuid
from dataclasses import dataclass
from datetime import timedelta
from typing import Any, cast

from sqlalchemy import CursorResult, select, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from via_api.config import Settings
from via_api.emails import EmailMessage, EmailSender
from via_api.errors import APIError
from via_api.models import (
    Organization,
    OrganizationMembership,
    PasswordResetToken,
    User,
    UserSession,
)
from via_api.models.base import utcnow
from via_api.models.enums import OrganizationRole
from via_api.security import (
    hash_password,
    hash_token,
    needs_rehash,
    new_token,
    password_problems,
    verify_password,
)
from via_api.services import activity
from via_api.services.activity import ClientInfo

INVALID_CREDENTIALS = "Invalid email or password."
#: Last-seen timestamps are written at most this often per session.
TOUCH_INTERVAL = timedelta(minutes=5)


@dataclass
class AuthContext:
    user: User
    session: UserSession | None  # None for future non-session auth (e.g. API keys)


def _check_password(password: str, email: str | None) -> None:
    problems = password_problems(password, email)
    if problems:
        raise APIError(422, "weak_password", " ".join(problems), {"problems": problems})


def organizations_for(db: Session, user_id: uuid.UUID) -> list[tuple[Organization, OrganizationRole]]:
    rows = db.execute(
        select(Organization, OrganizationMembership.role)
        .join(OrganizationMembership, OrganizationMembership.organization_id == Organization.id)
        .where(OrganizationMembership.user_id == user_id)
        .order_by(Organization.is_personal.desc(), Organization.name)
    ).all()
    return [(org, role) for org, role in rows]


def register(db: Session, *, email: str, password: str, display_name: str, client: ClientInfo) -> User:
    _check_password(password, email)
    if db.scalar(select(User.id).where(User.email == email)) is not None:
        raise APIError(409, "email_taken", "An account with this email already exists.")
    user = User(email=email, password_hash=hash_password(password), display_name=display_name)
    db.add(user)
    try:
        db.flush()
    except IntegrityError as exc:  # concurrent registration with the same email
        db.rollback()
        raise APIError(409, "email_taken", "An account with this email already exists.") from exc
    org = Organization(
        name=f"{display_name}'s workspace"[:120],
        slug=f"u-{user.id.hex[:16]}",
        is_personal=True,
        created_by_id=user.id,
    )
    db.add(org)
    db.flush()
    db.add(OrganizationMembership(organization_id=org.id, user_id=user.id, role=OrganizationRole.OWNER))
    activity.record(db, activity.USER_REGISTERED, actor_id=user.id, client=client, organization_id=org.id)
    return user


def authenticate(db: Session, *, email: str, password: str, client: ClientInfo) -> User:
    user = db.scalar(select(User).where(User.email == email))
    ok = verify_password(user.password_hash if user else None, password)
    if not ok or user is None or not user.is_active:
        activity.record(
            db,
            activity.LOGIN_FAILED,
            actor_id=user.id if user else None,
            client=client,
            # Record the attempted email only for existing accounts (no PII for random strings).
            details={"reason": "invalid_credentials"} if user else {"reason": "unknown_account"},
        )
        db.commit()
        raise APIError(401, "invalid_credentials", INVALID_CREDENTIALS)
    if needs_rehash(user.password_hash):
        user.password_hash = hash_password(password)
    user.last_login_at = utcnow()
    activity.record(db, activity.LOGIN_SUCCEEDED, actor_id=user.id, client=client)
    return user


def create_session(db: Session, user: User, settings: Settings, client: ClientInfo) -> tuple[UserSession, str]:
    token = new_token()
    now = utcnow()
    session = UserSession(
        user_id=user.id,
        token_hash=hash_token(token),
        expires_at=now + timedelta(hours=settings.session_ttl_hours),
        last_seen_at=now,
        ip_address=client.ip_address,
        user_agent=(client.user_agent or "")[:512] or None,
    )
    db.add(session)
    db.flush()
    return session, token


def resolve_session(db: Session, token: str) -> AuthContext | None:
    """Return the user for a valid, unexpired, unrevoked session token."""
    session = db.scalar(select(UserSession).where(UserSession.token_hash == hash_token(token)))
    now = utcnow()
    if session is None or session.revoked_at is not None or session.expires_at <= now:
        return None
    user = db.get(User, session.user_id)
    if user is None or not user.is_active:
        return None
    if now - session.last_seen_at > TOUCH_INTERVAL:
        session.last_seen_at = now
        db.commit()
    return AuthContext(user=user, session=session)


def revoke_session(db: Session, session: UserSession) -> None:
    if session.revoked_at is None:
        session.revoked_at = utcnow()


def revoke_all_sessions(db: Session, user_id: uuid.UUID, *, except_session_id: uuid.UUID | None = None) -> int:
    stmt = (
        update(UserSession)
        .where(UserSession.user_id == user_id, UserSession.revoked_at.is_(None))
        .values(revoked_at=utcnow())
    )
    if except_session_id is not None:
        stmt = stmt.where(UserSession.id != except_session_id)
    result = cast(CursorResult[Any], db.execute(stmt))
    return result.rowcount or 0


def active_sessions(db: Session, user_id: uuid.UUID) -> list[UserSession]:
    return list(
        db.scalars(
            select(UserSession)
            .where(UserSession.user_id == user_id, UserSession.revoked_at.is_(None), UserSession.expires_at > utcnow())
            .order_by(UserSession.last_seen_at.desc())
        )
    )


def change_password(
    db: Session, ctx: AuthContext, *, current_password: str, new_password: str, client: ClientInfo
) -> int:
    if not verify_password(ctx.user.password_hash, current_password):
        raise APIError(400, "invalid_password", "Your current password is incorrect.")
    _check_password(new_password, ctx.user.email)
    ctx.user.password_hash = hash_password(new_password)
    revoked = revoke_all_sessions(db, ctx.user.id, except_session_id=ctx.session.id if ctx.session else None)
    activity.record(
        db, activity.PASSWORD_CHANGED, actor_id=ctx.user.id, client=client, details={"other_sessions_revoked": revoked}
    )
    return revoked


def request_password_reset(
    db: Session, *, email: str, settings: Settings, sender: EmailSender, client: ClientInfo
) -> None:
    """Always succeeds from the caller's point of view (no account enumeration)."""
    user = db.scalar(select(User).where(User.email == email))
    if user is None or not user.is_active:
        return
    token = new_token()
    db.add(
        PasswordResetToken(
            user_id=user.id,
            token_hash=hash_token(token),
            expires_at=utcnow() + timedelta(minutes=settings.password_reset_ttl_minutes),
            requested_ip=client.ip_address,
        )
    )
    activity.record(db, activity.PASSWORD_RESET_REQUESTED, actor_id=user.id, client=client)
    db.commit()
    link = f"{settings.public_web_url.rstrip('/')}/reset-password?token={token}"
    sender.send(
        EmailMessage(
            to=user.email,
            subject="Reset your VIA password",
            body=(
                f"Hi {user.display_name},\n\nUse this link to choose a new password. It expires in "
                f"{settings.password_reset_ttl_minutes} minutes and can be used once:\n\n{link}\n\n"
                "If you didn't ask for this, you can ignore this email."
            ),
        )
    )


def confirm_password_reset(db: Session, *, token: str, new_password: str, client: ClientInfo) -> User:
    reset = db.scalar(select(PasswordResetToken).where(PasswordResetToken.token_hash == hash_token(token)))
    if reset is None or reset.used_at is not None or reset.expires_at <= utcnow():
        raise APIError(400, "invalid_reset_token", "This reset link is invalid or has expired. Request a new one.")
    user = db.get(User, reset.user_id)
    if user is None or not user.is_active:
        raise APIError(400, "invalid_reset_token", "This reset link is invalid or has expired. Request a new one.")
    _check_password(new_password, user.email)
    user.password_hash = hash_password(new_password)
    now = utcnow()
    reset.used_at = now
    # Invalidate every other outstanding reset token and all sessions.
    db.execute(
        update(PasswordResetToken)
        .where(PasswordResetToken.user_id == user.id, PasswordResetToken.used_at.is_(None))
        .values(used_at=now)
    )
    revoke_all_sessions(db, user.id)
    activity.record(db, activity.PASSWORD_RESET_COMPLETED, actor_id=user.id, client=client)
    return user
