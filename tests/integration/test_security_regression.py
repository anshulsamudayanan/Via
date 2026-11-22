"""Route-wide security regression suite.

The other integration tests check specific endpoints. These tests walk *every* route the
API exposes, so a new endpoint that forgets authentication, CSRF protection or the
project access check fails here, even if nobody wrote a test for it:

- every route must be classified as public or authenticated (unclassified routes fail);
- every authenticated route answers 401 without a session;
- every unsafe route refuses cookie-authenticated requests without the CSRF header;
- every route that takes a project, design, revision, file, organization or session id
  answers 404 to a signed-in user who has no access, and changes nothing;
- each rate limit is enforced on its real endpoint;
- the app never takes the client address from request headers.
"""

from __future__ import annotations

import re
import uuid
from pathlib import Path

import pytest
from fastapi.routing import APIRoute, iter_route_contexts

from tests.integration.conftest import register
from via_api import ratelimit
from via_api.routes.pcb import UPLOADS_PER_USER

REF = (Path(__file__).resolve().parents[1] / "engineering" / "fixtures" / "via_reference_v8.kicad_pcb").read_bytes()

PUBLIC = {
    ("GET", "/api/v1/health"),
    ("GET", "/api/v1/health/ready"),
    ("POST", "/api/v1/auth/register"),
    ("POST", "/api/v1/auth/login"),
    ("POST", "/api/v1/auth/password-reset/request"),
    ("POST", "/api/v1/auth/password-reset/confirm"),
}

#: Authenticated routes whose project comes from the `project_id` query parameter.
QUERY_SCOPED = {
    ("GET", "/api/v1/designs"),
    ("GET", "/api/v1/files"),
    ("GET", "/api/v1/activity"),
}

#: Valid request bodies for write routes, so access checks are reached instead of a 422.
#: A new write route with a body needs an entry here (the 404 test fails with a 422 otherwise).
BODIES = {
    ("PATCH", "/api/v1/projects/{project_id}"): {"name": "pwned"},
    ("POST", "/api/v1/projects/{project_id}/members"): {"email": "{stranger_email}", "role": "editor"},
    ("PATCH", "/api/v1/projects/{project_id}/members/{user_id}"): {"role": "viewer"},
    ("PATCH", "/api/v1/designs/{design_id}"): {"name": "pwned"},
}

UNSAFE = {"POST", "PUT", "PATCH", "DELETE"}


def api_routes(app) -> set[tuple[str, str]]:
    """Every (method, path) the app serves, including routes from included routers."""
    return {
        (method, ctx.path)
        for ctx in iter_route_contexts(app.routes)
        if isinstance(ctx.route, APIRoute)
        for method in ctx.methods or ()
        if method not in {"HEAD", "OPTIONS"}
    }


def fill(path: str, ids: dict[str, str]) -> str:
    return re.sub(r"\{(\w+)\}", lambda m: ids[m.group(1)], path)


def send(client, method: str, path: str, ids: dict[str, str], query: str = ""):
    url = fill(path, ids) + query
    if (method, path) == ("POST", "/api/v1/pcb/import"):
        return client.post(
            url,
            data={"project_id": ids["project_id"]},
            files={"file": ("board.kicad_pcb", REF, "application/octet-stream")},
        )
    body = BODIES.get((method, path))
    if body is not None:
        body = {k: v.format(**ids) if isinstance(v, str) else v for k, v in body.items()}
    return client.request(method, url, json=body)


@pytest.fixture
def world(make_client, db):
    """An owner with a parsed design in a private project, and a signed-in stranger."""
    owner, stranger = make_client(), make_client()
    owner_me = register(owner, "owner@example.com", "Owner")
    register(stranger, "stranger@example.com", "Stranger")
    project = owner.post("/api/v1/projects", json={"name": "Private board"}).json()
    imported = owner.post(
        "/api/v1/pcb/import",
        data={"project_id": project["id"]},
        files={"file": ("board.kicad_pcb", REF, "application/octet-stream")},
    ).json()
    assert imported["revision"]["status"] == "ready", imported
    files = owner.get(f"/api/v1/files?project_id={project['id']}").json()
    sessions = owner.get("/api/v1/auth/sessions").json()
    org_id = owner.get("/api/v1/organizations").json()[0]["id"]
    ids = {
        "project_id": project["id"],
        "design_id": imported["design"]["id"],
        "revision_id": imported["revision"]["id"],
        "file_id": files[0]["id"],
        "organization_id": org_id,
        "session_id": sessions[0]["id"],
        "user_id": owner_me["user"]["id"],
        "stranger_email": "stranger@example.com",
    }
    return owner, stranger, ids


def test_every_route_is_classified(app):
    routes = api_routes(app)
    assert routes >= PUBLIC, f"stale PUBLIC entries: {PUBLIC - routes}"
    assert routes >= QUERY_SCOPED, f"stale QUERY_SCOPED entries: {QUERY_SCOPED - routes}"
    assert set(BODIES) <= routes, f"stale BODIES entries: {set(BODIES) - routes}"
    # Everything not public must require a session (checked below); a route whose path
    # isn't under /api/v1 would escape the CSRF middleware and versioning.
    assert all(path.startswith("/api/v1/") for _, path in routes)


def test_every_authenticated_route_requires_a_session(app, make_client):
    anonymous = make_client()
    ids = {name: str(uuid.uuid4()) for name in ("project_id", "design_id", "revision_id", "file_id")}
    ids |= {name: str(uuid.uuid4()) for name in ("organization_id", "session_id", "user_id")}
    ids["stranger_email"] = "nobody@example.com"
    checked = 0
    for method, path in sorted(api_routes(app) - PUBLIC):
        query = f"?project_id={ids['project_id']}" if (method, path) in QUERY_SCOPED else ""
        resp = send(anonymous, method, path, ids, query)
        assert resp.status_code == 401, (method, path, resp.status_code, resp.text[:200])
        assert resp.json()["error"]["code"] == "unauthorized"
        checked += 1
    assert checked >= 40  # sanity: the walk really covered the API


def test_every_unsafe_route_requires_the_csrf_header(app, world, make_client):
    owner, _, ids = world
    # Same session cookie, but no X-VIA-Request header: what a cross-site form post looks like.
    forged = make_client(csrf=False)
    forged.cookies.update(owner.cookies)
    for method, path in sorted(r for r in api_routes(app) if r[0] in UNSAFE):
        resp = send(forged, method, path, ids)
        assert resp.status_code == 403, (method, path, resp.status_code)
        assert resp.json()["error"]["code"] == "csrf_failed"
    # Nothing happened: the session, project and design are intact.
    assert owner.get(f"/api/v1/projects/{ids['project_id']}").json()["name"] == "Private board"
    assert owner.get(f"/api/v1/designs/{ids['design_id']}").status_code == 200


def test_every_scoped_route_hides_other_users_data(app, world):
    owner, stranger, ids = world
    id_params = {"project_id", "design_id", "revision_id", "file_id", "organization_id", "session_id"}
    checked: list[tuple[str, str]] = []
    for method, path in sorted(api_routes(app) - PUBLIC):
        params = set(re.findall(r"\{(\w+)\}", path))
        scoped = (method, path) in QUERY_SCOPED or (method, path) == ("POST", "/api/v1/pcb/import")
        if not (params & id_params or scoped):
            continue
        query = f"?project_id={ids['project_id']}" if (method, path) in QUERY_SCOPED else ""
        resp = send(stranger, method, path, ids, query)
        assert resp.status_code == 404, (method, path, resp.status_code, resp.text[:200])
        assert resp.json()["error"]["code"] == "not_found"
        checked.append((method, path))
    assert len(checked) >= 25, checked

    # The owner's data is untouched.
    project = owner.get(f"/api/v1/projects/{ids['project_id']}").json()
    assert project["name"] == "Private board"
    assert project["archived_at"] is None
    members = owner.get(f"/api/v1/projects/{ids['project_id']}/members").json()
    assert [(m["user"]["id"], m["role"]) for m in members] == [(ids["user_id"], "owner")]
    assert owner.get(f"/api/v1/designs/{ids['design_id']}").json()["name"] == "board"
    assert owner.get(f"/api/v1/ai/consent/{ids['project_id']}").json()["granted"] is False
    assert owner.get("/api/v1/auth/me").status_code == 200  # session not revoked


@pytest.mark.parametrize(
    ("limit", "key", "method", "path", "body"),
    [
        (ratelimit.REGISTER_PER_IP, "testclient", "post", "/api/v1/auth/register",
         {"email": "new@example.com", "password": "correct horse battery", "display_name": "N"}),
        (ratelimit.LOGIN_PER_IP, "testclient", "post", "/api/v1/auth/login",
         {"email": "owner@example.com", "password": "correct horse battery"}),
        (ratelimit.PASSWORD_RESET_PER_IP, "testclient", "post", "/api/v1/auth/password-reset/request",
         {"email": "owner@example.com"}),
        (ratelimit.PASSWORD_CHANGE_PER_USER, "{user_id}", "post", "/api/v1/users/me/password",
         {"current_password": "correct horse battery", "new_password": "another horse battery"}),
        (ratelimit.MEMBER_LOOKUP_PER_USER, "{user_id}", "post", "/api/v1/projects/{project_id}/members",
         {"email": "stranger@example.com", "role": "viewer"}),
    ],
    ids=["register", "login", "password-reset", "password-change", "member-lookup"],
)  # fmt: skip
def test_rate_limits_are_enforced(world, test_redis, limit, key, method, path, body):
    owner, _, ids = world
    # Fill the window up to its budget, then the next real request must be refused.
    test_redis.set(f"via:rl:{limit.name}:{key.format(**ids)}", limit.max_requests, ex=limit.window_seconds)
    resp = getattr(owner, method)(fill(path, ids), json=body)
    assert resp.status_code == 429, (limit.name, resp.status_code, resp.text[:200])
    assert resp.json()["error"]["details"]["retry_after_seconds"] >= 1


def test_upload_rate_limit(world, test_redis):
    owner, _, ids = world
    test_redis.set(f"via:rl:{UPLOADS_PER_USER.name}:{ids['user_id']}", UPLOADS_PER_USER.max_requests, ex=60)
    resp = send(owner, "POST", "/api/v1/pcb/import", ids)
    assert resp.status_code == 429


def test_account_lockout_blocks_even_the_right_password(client, test_redis):
    register(client, "victim@example.com")
    wrong = {"email": "victim@example.com", "password": "x" * 12}
    for _ in range(ratelimit.LOGIN_PER_ACCOUNT.max_requests):
        assert client.post("/api/v1/auth/login", json=wrong).status_code == 401
    # Even the right password is refused once the account's budget is spent.
    resp = client.post("/api/v1/auth/login", json={"email": "victim@example.com", "password": "correct horse battery"})
    assert resp.status_code == 429


def test_client_address_is_never_taken_from_request_headers(make_client):
    """Only the ASGI server may rewrite the client address, and only for trusted proxies
    (`VIA_FORWARDED_ALLOW_IPS`). The app itself must ignore spoofable headers, or per-IP
    rate limits could be dodged by sending a different X-Forwarded-For each time."""
    c = make_client()
    c.headers.update({"X-Forwarded-For": "6.6.6.6", "X-Real-IP": "6.6.6.6", "Forwarded": "for=6.6.6.6"})
    register(c, "spoof@example.com")
    assert c.get("/api/v1/auth/sessions").json()[0]["ip_address"] == "testclient"


def test_uploaded_filenames_cannot_escape_or_inject(world, db):
    owner, _, ids = world
    resp = owner.post(
        "/api/v1/pcb/import",
        data={"project_id": ids["project_id"]},
        files={"file": ("../../etc/<script>x</script>\\..\\evil.kicad_pcb", REF + b"\n", "application/octet-stream")},
    )
    assert resp.status_code == 202, resp.text
    design = resp.json()["design"]
    assert "/" not in design["name"] and "\\" not in design["name"] and ".." not in design["name"]
    assert design["name"] == "evil"
    assert design["current_revision"]["source_file"]["original_filename"] == "evil.kicad_pcb"
    for f in owner.get(f"/api/v1/files?project_id={ids['project_id']}").json():
        assert "storage_key" not in f  # the storage layout is never exposed
