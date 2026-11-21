"""Authentication, session and user schemas."""

from __future__ import annotations

import uuid
from datetime import datetime

from pydantic import BaseModel, Field

from via_api.models.enums import OrganizationRole
from via_api.schemas.common import APIModel, Email, Name
from via_api.security import MAX_PASSWORD_LENGTH

Password = Field(min_length=1, max_length=MAX_PASSWORD_LENGTH)


class RegisterRequest(BaseModel):
    email: Email
    password: str = Password
    display_name: Name


class LoginRequest(BaseModel):
    email: Email
    password: str = Password
    #: Programmatic clients: return the session token in the body (for
    #: ``Authorization: Bearer``) instead of setting a cookie. Browsers never use this.
    issue_token: bool = False


class UserOut(APIModel):
    id: uuid.UUID
    email: str
    display_name: str
    email_verified_at: datetime | None
    created_at: datetime


class OrganizationSummary(APIModel):
    id: uuid.UUID
    name: str
    slug: str
    is_personal: bool
    role: OrganizationRole


class MeResponse(BaseModel):
    user: UserOut
    organizations: list[OrganizationSummary]


class AuthResponse(MeResponse):
    """Returned by register/login.

    Browsers receive the session as an httpOnly cookie and ``session_token`` is
    null. It is only populated for ``LoginRequest.issue_token``.
    """

    session_token: str | None = None


class SessionOut(APIModel):
    id: uuid.UUID
    created_at: datetime
    last_seen_at: datetime
    expires_at: datetime
    ip_address: str | None
    user_agent: str | None
    current: bool = False


class PasswordResetRequest(BaseModel):
    email: Email


class PasswordResetConfirm(BaseModel):
    token: str = Field(min_length=20, max_length=200)
    new_password: str = Password


class UpdateMeRequest(BaseModel):
    display_name: Name


class ChangePasswordRequest(BaseModel):
    current_password: str = Password
    new_password: str = Password


class Message(BaseModel):
    message: str
