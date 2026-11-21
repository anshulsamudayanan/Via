"""Authentication: registration, login, sessions, CSRF, rate limits, password reset."""

from __future__ import annotations

import re

from sqlalchemy import select

from tests.integration.conftest import PASSWORD, register
from via_api.models import ActivityLog, Organization, OrganizationMembership, User, UserSession
from via_api.security import hash_token


def test_register_creates_user_personal_org_and_session(client, db):
    body = register(client, "Ada@Example.com ", "Ada Lovelace")
    assert body["user"]["email"] == "ada@example.com"  # normalized
    assert body["session_token"] is None  # browsers never get the token in the body
    (org,) = body["organizations"]
    assert org["is_personal"] is True and org["role"] == "owner"

    cookie = client.cookies.get("via_session")
    assert cookie
    user = db.scalar(select(User).where(User.email == "ada@example.com"))
    assert user.password_hash.startswith("$argon2id$")
    assert PASSWORD not in user.password_hash
    session = db.scalar(select(UserSession).where(UserSession.user_id == user.id))
    assert session.token_hash == hash_token(cookie)  # only the hash is stored
    assert cookie not in session.token_hash
    assert db.scalar(select(OrganizationMembership).where(OrganizationMembership.user_id == user.id)).role == "owner"
    assert client.get("/api/v1/auth/me").json()["user"]["display_name"] == "Ada Lovelace"


def test_session_cookie_flags(client):
    resp = client.post(
        "/api/v1/auth/register", json={"email": "c@example.com", "password": PASSWORD, "display_name": "C"}
    )
    set_cookie = resp.headers["set-cookie"].lower()
    assert "httponly" in set_cookie
    assert "samesite=lax" in set_cookie
    assert "path=/" in set_cookie
    assert "secure" not in set_cookie  # development; production defaults to Secure


def test_duplicate_email_is_rejected(client, make_client):
    register(client, "dup@example.com")
    resp = make_client().post(
        "/api/v1/auth/register", json={"email": "DUP@example.com", "password": PASSWORD, "display_name": "X"}
    )
    assert resp.status_code == 409
    assert resp.json()["error"]["code"] == "email_taken"


def test_weak_and_invalid_registration_input(client):
    weak = client.post(
        "/api/v1/auth/register", json={"email": "w@example.com", "password": "short", "display_name": "W"}
    )
    assert weak.status_code == 422 and weak.json()["error"]["code"] == "weak_password"
    same = client.post(
        "/api/v1/auth/register",
        json={"email": "same@example.com", "password": "same@example.com", "display_name": "S"},
    )
    assert same.json()["error"]["code"] == "weak_password"
    bad_email = client.post("/api/v1/auth/register", json={"email": "nope", "password": PASSWORD, "display_name": "B"})
    assert bad_email.status_code == 422 and bad_email.json()["error"]["code"] == "validation_error"
    too_long = client.post(
        "/api/v1/auth/register", json={"email": "l@example.com", "password": "x" * 129, "display_name": "L"}
    )
    assert too_long.status_code == 422


def test_login_logout_and_relogin(client, make_client):
    register(client, "user@example.com")
    other = make_client()
    resp = other.post("/api/v1/auth/login", json={"email": "USER@example.com", "password": PASSWORD})
    assert resp.status_code == 200
    assert other.get("/api/v1/auth/me").status_code == 200

    assert other.post("/api/v1/auth/logout").status_code == 200
    assert other.get("/api/v1/auth/me").status_code == 401
    # The first session is unaffected by the other device logging out.
    assert client.get("/api/v1/auth/me").status_code == 200


def test_logged_out_token_cannot_be_replayed(client, make_client):
    register(client, "replay@example.com")
    token = client.cookies.get("via_session")
    client.post("/api/v1/auth/logout")
    attacker = make_client()
    attacker.cookies.set("via_session", token)
    assert attacker.get("/api/v1/auth/me").status_code == 401


def test_wrong_password_and_unknown_email_get_the_same_answer(client, db):
    register(client, "known@example.com")
    a = client.post("/api/v1/auth/login", json={"email": "known@example.com", "password": "wrong password!!"})
    b = client.post("/api/v1/auth/login", json={"email": "unknown@example.com", "password": "wrong password!!"})
    assert a.status_code == b.status_code == 401
    assert a.json()["error"]["message"] == b.json()["error"]["message"] == "Invalid email or password."
    failures = db.scalars(select(ActivityLog).where(ActivityLog.action == "auth.login_failed")).all()
    assert len(failures) == 2
    assert all("password" not in str(f.details) for f in failures)


def test_unauthenticated_requests_are_rejected(make_client):
    anon = make_client()
    for method, path in [
        ("get", "/api/v1/auth/me"),
        ("get", "/api/v1/auth/sessions"),
        ("get", "/api/v1/users/me"),
        ("patch", "/api/v1/users/me"),
        ("post", "/api/v1/auth/logout"),
    ]:
        resp = getattr(anon, method)(path, **({"json": {"display_name": "x"}} if method == "patch" else {}))
        assert resp.status_code == 401, path
        assert resp.json()["error"]["code"] == "unauthorized"


def test_garbage_and_oversized_tokens_are_rejected(make_client):
    c = make_client()
    c.cookies.set("via_session", "not-a-real-token")
    assert c.get("/api/v1/auth/me").status_code == 401
    assert c.get("/api/v1/auth/me", headers={"Authorization": "Bearer " + "x" * 5000}).status_code == 401


def test_bearer_token_for_programmatic_clients(client, make_client):
    register(client, "bot@example.com")
    api = make_client(csrf=False)
    resp = api.post(
        "/api/v1/auth/login",
        json={"email": "bot@example.com", "password": PASSWORD, "issue_token": True},
        headers={"X-VIA-Request": "1"},
    )
    token = resp.json()["session_token"]
    assert token and "set-cookie" not in resp.headers
    headers = {"Authorization": f"Bearer {token}"}
    assert api.get("/api/v1/auth/me", headers=headers).status_code == 200
    # Bearer requests are exempt from the CSRF header (not sent automatically by browsers).
    assert api.patch("/api/v1/users/me", json={"display_name": "Bot"}, headers=headers).status_code == 200


def test_csrf_header_required_for_unsafe_requests(make_client):
    no_csrf = make_client(csrf=False)
    resp = no_csrf.post(
        "/api/v1/auth/register", json={"email": "x@example.com", "password": PASSWORD, "display_name": "X"}
    )
    assert resp.status_code == 403
    assert resp.json()["error"]["code"] == "csrf_failed"
    assert resp.headers["x-request-id"]  # still wrapped by the request-context middleware
    assert no_csrf.get("/api/v1/health").status_code == 200  # safe methods unaffected


def test_expired_sessions_are_rejected(client, db):
    register(client, "exp@example.com")
    session = db.scalar(select(UserSession).join(User).where(User.email == "exp@example.com"))
    from datetime import timedelta

    session.expires_at = session.created_at - timedelta(seconds=1)
    db.flush()
    assert client.get("/api/v1/auth/me").status_code == 401


def test_deactivated_users_lose_access(client, db):
    register(client, "gone@example.com")
    db.scalar(select(User).where(User.email == "gone@example.com")).is_active = False
    db.flush()
    assert client.get("/api/v1/auth/me").status_code == 401
    login = client.post("/api/v1/auth/login", json={"email": "gone@example.com", "password": PASSWORD})
    assert login.status_code == 401


def test_list_and_revoke_sessions(client, make_client):
    register(client, "multi@example.com")
    laptop = make_client()
    laptop.post("/api/v1/auth/login", json={"email": "multi@example.com", "password": PASSWORD})
    sessions = client.get("/api/v1/auth/sessions").json()
    assert len(sessions) == 2
    assert sum(s["current"] for s in sessions) == 1
    laptop_session = next(s for s in sessions if not s["current"])
    assert client.delete(f"/api/v1/auth/sessions/{laptop_session['id']}").status_code == 204
    assert laptop.get("/api/v1/auth/me").status_code == 401
    assert client.get("/api/v1/auth/me").status_code == 200


def test_cannot_revoke_another_users_session(client, make_client, db):
    register(client, "victim@example.com")
    victim_session = db.scalar(select(UserSession).join(User).where(User.email == "victim@example.com"))
    attacker = make_client()
    register(attacker, "attacker@example.com")
    assert attacker.delete(f"/api/v1/auth/sessions/{victim_session.id}").status_code == 404
    assert client.get("/api/v1/auth/me").status_code == 200


def test_login_rate_limit_per_account(client, make_client):
    register(client, "target@example.com")
    attacker = make_client()
    codes = [
        attacker.post(
            "/api/v1/auth/login", json={"email": "target@example.com", "password": "guess-guess-1"}
        ).status_code
        for _ in range(9)
    ]
    assert codes[:8] == [401] * 8
    assert codes[8] == 429
    resp = attacker.post("/api/v1/auth/login", json={"email": "target@example.com", "password": PASSWORD})
    assert resp.status_code == 429  # even the right password, until the window passes
    assert resp.json()["error"]["details"]["retry_after_seconds"] >= 1


def test_rate_limiter_fails_open_when_redis_is_down(app, make_client):
    from redis import Redis

    from via_api.redis_client import get_redis

    app.dependency_overrides[get_redis] = lambda: Redis.from_url("redis://127.0.0.1:1/0", socket_connect_timeout=0.2)
    c = make_client()
    register(c, "open@example.com")
    assert c.get("/api/v1/auth/me").status_code == 200


def test_profile_update(client):
    register(client, "p@example.com", "Old Name")
    resp = client.patch("/api/v1/users/me", json={"display_name": "  New Name  "})
    assert resp.status_code == 200 and resp.json()["user"]["display_name"] == "New Name"
    assert client.patch("/api/v1/users/me", json={"display_name": ""}).status_code == 422
    assert client.patch("/api/v1/users/me", json={"display_name": "bad\x00name"}).status_code == 422


def test_change_password_revokes_other_sessions(client, make_client):
    register(client, "chg@example.com")
    other = make_client()
    other.post("/api/v1/auth/login", json={"email": "chg@example.com", "password": PASSWORD})
    wrong = client.post(
        "/api/v1/users/me/password", json={"current_password": "nope-nope-nope", "new_password": "new password 123"}
    )
    assert wrong.status_code == 400
    ok = client.post(
        "/api/v1/users/me/password", json={"current_password": PASSWORD, "new_password": "new password 123"}
    )
    assert ok.status_code == 200
    assert client.get("/api/v1/auth/me").status_code == 200  # current session kept
    assert other.get("/api/v1/auth/me").status_code == 401  # others signed out
    fresh = make_client()
    assert fresh.post("/api/v1/auth/login", json={"email": "chg@example.com", "password": PASSWORD}).status_code == 401
    assert (
        fresh.post("/api/v1/auth/login", json={"email": "chg@example.com", "password": "new password 123"}).status_code
        == 200
    )


def _reset_token(mailer) -> str:
    match = re.search(r"token=([A-Za-z0-9_-]+)", mailer.sent[-1].body)
    assert match
    return match.group(1)


def test_password_reset_flow(client, make_client, mailer, db):
    register(client, "reset@example.com")
    anon = make_client()
    resp = anon.post("/api/v1/auth/password-reset/request", json={"email": "reset@example.com"})
    assert resp.status_code == 202
    assert mailer.sent[-1].to == "reset@example.com"
    assert "http://localhost:3000/reset-password?token=" in mailer.sent[-1].body
    token = _reset_token(mailer)

    weak = anon.post("/api/v1/auth/password-reset/confirm", json={"token": token, "new_password": "short"})
    assert weak.status_code == 422
    ok = anon.post("/api/v1/auth/password-reset/confirm", json={"token": token, "new_password": "brand new secret 9"})
    assert ok.status_code == 200
    assert client.get("/api/v1/auth/me").status_code == 401  # all sessions revoked
    again = anon.post("/api/v1/auth/password-reset/confirm", json={"token": token, "new_password": "another secret 99"})
    assert again.status_code == 400 and again.json()["error"]["code"] == "invalid_reset_token"  # single use
    assert (
        anon.post(
            "/api/v1/auth/login", json={"email": "reset@example.com", "password": "brand new secret 9"}
        ).status_code
        == 200
    )
    assert db.scalar(select(ActivityLog).where(ActivityLog.action == "auth.password_reset_completed")) is not None


def test_password_reset_does_not_reveal_accounts(make_client, mailer):
    anon = make_client()
    resp = anon.post("/api/v1/auth/password-reset/request", json={"email": "nobody@example.com"})
    assert resp.status_code == 202
    assert resp.json()["message"] == "If an account exists for that email, a reset link has been sent."
    assert mailer.sent == []


def test_password_reset_tokens_expire(client, make_client, mailer, db):
    from datetime import timedelta

    from via_api.models import PasswordResetToken

    register(client, "late@example.com")
    anon = make_client()
    anon.post("/api/v1/auth/password-reset/request", json={"email": "late@example.com"})
    token = _reset_token(mailer)
    row = db.scalar(select(PasswordResetToken).where(PasswordResetToken.token_hash == hash_token(token)))
    row.expires_at = row.created_at - timedelta(seconds=1)
    db.flush()
    resp = anon.post("/api/v1/auth/password-reset/confirm", json={"token": token, "new_password": "brand new secret 9"})
    assert resp.status_code == 400


def test_new_users_own_exactly_one_personal_org(client, db):
    register(client, "solo@example.com")
    user = db.scalar(select(User).where(User.email == "solo@example.com"))
    orgs = db.scalars(select(Organization).where(Organization.created_by_id == user.id)).all()
    assert len(orgs) == 1 and orgs[0].is_personal
