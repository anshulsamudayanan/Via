"""FastAPI dependencies shared by routes."""

from __future__ import annotations

from typing import Annotated

from fastapi import Depends, Request
from redis import Redis
from sqlalchemy.orm import Session

from via_api.config import Environment, Settings, get_settings
from via_api.db import get_db
from via_api.emails import DisabledEmailSender, EmailSender, LogEmailSender
from via_api.errors import APIError
from via_api.ratelimit import RateLimiter
from via_api.redis_client import get_redis
from via_api.services.activity import ClientInfo
from via_api.services.auth import AuthContext, resolve_session

DB = Annotated[Session, Depends(get_db)]
AppSettings = Annotated[Settings, Depends(get_settings)]


def client_info(request: Request) -> ClientInfo:
    return ClientInfo(
        ip_address=request.client.host if request.client else None,
        user_agent=request.headers.get("user-agent"),
    )


Client = Annotated[ClientInfo, Depends(client_info)]


def get_rate_limiter(redis: Annotated[Redis, Depends(get_redis)], settings: AppSettings) -> RateLimiter:
    return RateLimiter(redis, enabled=settings.rate_limit_enabled)


Limiter = Annotated[RateLimiter, Depends(get_rate_limiter)]


def get_email_sender(settings: AppSettings) -> EmailSender:
    return DisabledEmailSender() if settings.env == Environment.PRODUCTION else LogEmailSender()


Mailer = Annotated[EmailSender, Depends(get_email_sender)]


def session_token_from(request: Request, settings: Settings) -> str | None:
    auth = request.headers.get("authorization", "")
    if auth.lower().startswith("bearer "):
        return auth[7:].strip() or None
    return request.cookies.get(settings.session_cookie_name)


def optional_auth(request: Request, db: DB, settings: AppSettings) -> AuthContext | None:
    token = session_token_from(request, settings)
    if not token or len(token) > 200:
        return None
    return resolve_session(db, token)


def require_auth(ctx: Annotated[AuthContext | None, Depends(optional_auth)]) -> AuthContext:
    if ctx is None:
        raise APIError(401, "unauthorized", "Sign in to continue.")
    return ctx


CurrentAuth = Annotated[AuthContext, Depends(require_auth)]
