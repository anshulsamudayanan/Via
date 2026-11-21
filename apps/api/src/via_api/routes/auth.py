"""/api/v1/auth: registration, login, logout, sessions, password reset."""

from __future__ import annotations

import uuid

from fastapi import APIRouter, Response, status
from sqlalchemy.orm import Session

from via_api.config import Settings
from via_api.deps import DB, AppSettings, Client, CurrentAuth, Limiter, Mailer
from via_api.errors import error_responses, not_found
from via_api.models import User, UserSession
from via_api.ratelimit import LOGIN_PER_ACCOUNT, LOGIN_PER_IP, PASSWORD_RESET_PER_IP, REGISTER_PER_IP
from via_api.schemas.auth import (
    AuthResponse,
    LoginRequest,
    MeResponse,
    Message,
    OrganizationSummary,
    PasswordResetConfirm,
    PasswordResetRequest,
    RegisterRequest,
    SessionOut,
    UserOut,
)
from via_api.security import hash_token
from via_api.services import activity
from via_api.services import auth as auth_service

router = APIRouter(prefix="/auth", tags=["auth"])

_ERRORS = error_responses(401, 429)


def me_response(db: Session, user: User) -> MeResponse:
    orgs = [
        OrganizationSummary(id=o.id, name=o.name, slug=o.slug, is_personal=o.is_personal, role=role)
        for o, role in auth_service.organizations_for(db, user.id)
    ]
    return MeResponse(user=UserOut.model_validate(user), organizations=orgs)


def set_session_cookie(response: Response, token: str, settings: Settings) -> None:
    response.set_cookie(
        settings.session_cookie_name,
        token,
        max_age=settings.session_ttl_hours * 3600,
        httponly=True,
        secure=settings.cookie_secure,
        samesite="lax",
        path="/",
    )


def clear_session_cookie(response: Response, settings: Settings) -> None:
    response.delete_cookie(
        settings.session_cookie_name, path="/", httponly=True, secure=settings.cookie_secure, samesite="lax"
    )


@router.post(
    "/register",
    response_model=AuthResponse,
    status_code=status.HTTP_201_CREATED,
    responses=error_responses(401, 409, 429),
    summary="Create an account (signs the new user in)",
)
def register(
    body: RegisterRequest, response: Response, db: DB, settings: AppSettings, client: Client, limiter: Limiter
) -> AuthResponse:
    limiter.hit(REGISTER_PER_IP, client.ip_address or "unknown")
    user = auth_service.register(
        db, email=body.email, password=body.password, display_name=body.display_name, client=client
    )
    _, token = auth_service.create_session(db, user, settings, client)
    db.commit()
    set_session_cookie(response, token, settings)
    return AuthResponse(**me_response(db, user).model_dump())


@router.post("/login", response_model=AuthResponse, responses=_ERRORS, summary="Sign in")
def login(
    body: LoginRequest, response: Response, db: DB, settings: AppSettings, client: Client, limiter: Limiter
) -> AuthResponse:
    limiter.hit(LOGIN_PER_IP, client.ip_address or "unknown")
    limiter.hit(LOGIN_PER_ACCOUNT, hash_token(body.email))
    user = auth_service.authenticate(db, email=body.email, password=body.password, client=client)
    _, token = auth_service.create_session(db, user, settings, client)
    db.commit()
    result = AuthResponse(**me_response(db, user).model_dump())
    if body.issue_token:
        result.session_token = token
    else:
        set_session_cookie(response, token, settings)
    return result


@router.post("/logout", response_model=Message, summary="Sign out of the current session")
def logout(response: Response, db: DB, settings: AppSettings, client: Client, ctx: CurrentAuth) -> Message:
    if ctx.session is not None:
        auth_service.revoke_session(db, ctx.session)
    activity.record(db, activity.LOGGED_OUT, actor_id=ctx.user.id, client=client)
    db.commit()
    clear_session_cookie(response, settings)
    return Message(message="Signed out.")


@router.get("/me", response_model=MeResponse, responses=_ERRORS, summary="The signed-in user and their organizations")
def me(db: DB, ctx: CurrentAuth) -> MeResponse:
    return me_response(db, ctx.user)


@router.get("/sessions", response_model=list[SessionOut], summary="Active sessions of the signed-in user")
def list_sessions(db: DB, ctx: CurrentAuth) -> list[SessionOut]:
    current_id = ctx.session.id if ctx.session else None
    return [
        SessionOut.model_validate(s).model_copy(update={"current": s.id == current_id})
        for s in auth_service.active_sessions(db, ctx.user.id)
    ]


@router.delete(
    "/sessions/{session_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    responses=error_responses(404),
    summary="Revoke one of your sessions (sign out a device)",
)
def revoke_session(
    session_id: uuid.UUID, response: Response, db: DB, settings: AppSettings, client: Client, ctx: CurrentAuth
) -> None:
    target = db.get(UserSession, session_id)
    if target is None or target.user_id != ctx.user.id or target.revoked_at is not None:
        raise not_found("Session")
    auth_service.revoke_session(db, target)
    activity.record(
        db, activity.SESSION_REVOKED, actor_id=ctx.user.id, client=client, target_type="session", target_id=target.id
    )
    db.commit()
    if ctx.session is not None and target.id == ctx.session.id:
        clear_session_cookie(response, settings)


@router.post(
    "/password-reset/request",
    response_model=Message,
    status_code=status.HTTP_202_ACCEPTED,
    summary="Email a password reset link (always responds the same way)",
)
def request_password_reset(
    body: PasswordResetRequest, db: DB, settings: AppSettings, client: Client, limiter: Limiter, mailer: Mailer
) -> Message:
    limiter.hit(PASSWORD_RESET_PER_IP, client.ip_address or "unknown")
    auth_service.request_password_reset(db, email=body.email, settings=settings, sender=mailer, client=client)
    return Message(message="If an account exists for that email, a reset link has been sent.")


@router.post(
    "/password-reset/confirm",
    response_model=Message,
    responses=error_responses(400, 422),
    summary="Set a new password with a reset token (signs out all sessions)",
)
def confirm_password_reset(body: PasswordResetConfirm, db: DB, client: Client, limiter: Limiter) -> Message:
    limiter.hit(PASSWORD_RESET_PER_IP, client.ip_address or "unknown")
    auth_service.confirm_password_reset(db, token=body.token, new_password=body.new_password, client=client)
    db.commit()
    return Message(message="Your password has been changed. Sign in with your new password.")
