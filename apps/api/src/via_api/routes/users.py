"""/api/v1/users: the signed-in user's profile and password."""

from __future__ import annotations

from fastapi import APIRouter

from via_api.deps import DB, Client, CurrentAuth, Limiter
from via_api.errors import error_responses
from via_api.ratelimit import PASSWORD_CHANGE_PER_USER
from via_api.routes.auth import me_response
from via_api.schemas.auth import ChangePasswordRequest, MeResponse, Message, UpdateMeRequest
from via_api.services import activity
from via_api.services import auth as auth_service

router = APIRouter(prefix="/users", tags=["users"])


@router.get("/me", response_model=MeResponse, summary="Your profile")
def get_me(db: DB, ctx: CurrentAuth) -> MeResponse:
    return me_response(db, ctx.user)


@router.patch("/me", response_model=MeResponse, summary="Update your profile")
def update_me(body: UpdateMeRequest, db: DB, client: Client, ctx: CurrentAuth) -> MeResponse:
    if body.display_name != ctx.user.display_name:
        ctx.user.display_name = body.display_name
        activity.record(
            db, activity.PROFILE_UPDATED, actor_id=ctx.user.id, client=client, details={"fields": ["display_name"]}
        )
        db.commit()
    return me_response(db, ctx.user)


@router.post(
    "/me/password",
    response_model=Message,
    responses=error_responses(400, 422),
    summary="Change your password (signs out your other sessions)",
)
def change_password(body: ChangePasswordRequest, db: DB, client: Client, ctx: CurrentAuth, limiter: Limiter) -> Message:
    limiter.hit(PASSWORD_CHANGE_PER_USER, str(ctx.user.id))
    revoked = auth_service.change_password(
        db, ctx, current_password=body.current_password, new_password=body.new_password, client=client
    )
    db.commit()
    suffix = f" {revoked} other session(s) were signed out." if revoked else ""
    return Message(message=f"Password changed.{suffix}")
