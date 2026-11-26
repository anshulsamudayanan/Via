"""Security regression suite: private-project isolation and independent org/project permissions."""

from __future__ import annotations

import uuid

import pytest
from sqlalchemy import select

from tests.integration.conftest import register
from via_api.models import OrganizationMembership, User
from via_api.models.enums import OrganizationRole


@pytest.fixture
def alice_and_bob(make_client):
    alice, bob = make_client(), make_client()
    a = register(alice, "alice@example.com", "Alice")
    b = register(bob, "bob@example.com", "Bob")
    project = alice.post("/api/v1/projects", json={"name": "Alice secret board"}).json()
    return alice, bob, a, b, project


def project_endpoints(pid: str):
    other = uuid.uuid4()
    return [
        ("get", f"/api/v1/projects/{pid}", None),
        ("patch", f"/api/v1/projects/{pid}", {"name": "pwned"}),
        ("delete", f"/api/v1/projects/{pid}", None),
        ("post", f"/api/v1/projects/{pid}/archive", None),
        ("post", f"/api/v1/projects/{pid}/unarchive", None),
        ("get", f"/api/v1/projects/{pid}/members", None),
        ("post", f"/api/v1/projects/{pid}/members", {"email": "bob@example.com"}),
        ("patch", f"/api/v1/projects/{pid}/members/{other}", {"role": "viewer"}),
        ("delete", f"/api/v1/projects/{pid}/members/{other}", None),
        ("get", f"/api/v1/activity?project_id={pid}", None),
    ]


def call(client, method, path, body):
    return getattr(client, method)(path, **({"json": body} if body is not None else {}))


def test_private_project_is_invisible_to_other_users(alice_and_bob):
    alice, bob, _, _, project = alice_and_bob
    for method, path, body in project_endpoints(project["id"]):
        resp = call(bob, method, path, body)
        assert resp.status_code == 404, (method, path, resp.status_code)
        assert resp.json()["error"]["code"] == "not_found"
    # Indistinguishable from a project that doesn't exist.
    missing = bob.get(f"/api/v1/projects/{uuid.uuid4()}")
    assert missing.json()["error"]["message"] == bob.get(f"/api/v1/projects/{project['id']}").json()["error"]["message"]
    # Nothing changed for Alice.
    assert alice.get(f"/api/v1/projects/{project['id']}").json()["name"] == "Alice secret board"


def test_private_project_never_appears_in_lists_search_or_counts(alice_and_bob):
    _, bob, _, _, _ = alice_and_bob
    assert bob.get("/api/v1/projects?status=all").json()["total"] == 0
    assert bob.get("/api/v1/projects?q=secret&status=all").json()["items"] == []
    assert bob.get("/api/v1/projects/summary").json() == {
        "active": 0,
        "archived": 0,
        "designs": 0,
        "imports_7d": 0,
        "analyses_7d": 0,
    }


def test_activity_feed_is_isolated(alice_and_bob):
    alice, bob, _, _, project = alice_and_bob
    alice.patch(f"/api/v1/projects/{project['id']}", json={"name": "Renamed secret"})
    bob_feed = bob.get("/api/v1/activity").json()
    assert all(item["project"] is None for item in bob_feed["items"])
    assert {item["action"] for item in bob_feed["items"]} == {"user.registered"}  # only Bob's own events
    assert "Renamed secret" not in str(bob_feed)
    assert "alice" not in str(bob_feed).lower()


def test_unauthenticated_access_to_projects_is_rejected(make_client, alice_and_bob):
    _, _, _, _, project = alice_and_bob
    anon = make_client()
    for method, path, body in [
        *project_endpoints(project["id"]),
        ("get", "/api/v1/projects", None),
        ("post", "/api/v1/projects", {"name": "x"}),
    ]:
        assert call(anon, method, path, body).status_code == 401, path


def test_organization_admins_cannot_see_private_projects(alice_and_bob, db):
    alice, bob, a, b, project = alice_and_bob
    # Make Bob an admin of Alice's personal organization (no invitation API yet; set up directly).
    db.add(
        OrganizationMembership(
            organization_id=a["organizations"][0]["id"], user_id=b["user"]["id"], role=OrganizationRole.ADMIN
        )
    )
    db.flush()
    assert bob.get(f"/api/v1/organizations/{a['organizations'][0]['id']}").json()["role"] == "admin"
    # Organization membership alone grants nothing on a private project.
    assert bob.get(f"/api/v1/projects/{project['id']}").status_code == 404
    assert bob.get("/api/v1/projects").json()["total"] == 0

    # Organization-visible projects are readable (viewer) by organization members, not editable.
    alice.patch(f"/api/v1/projects/{project['id']}", json={"visibility": "organization"})
    shared = bob.get(f"/api/v1/projects/{project['id']}")
    assert shared.status_code == 200 and shared.json()["my_role"] == "viewer"
    assert bob.patch(f"/api/v1/projects/{project['id']}", json={"name": "x"}).status_code == 403
    assert bob.delete(f"/api/v1/projects/{project['id']}").status_code == 403

    # Back to private: access disappears immediately.
    alice.patch(f"/api/v1/projects/{project['id']}", json={"visibility": "private"})
    assert bob.get(f"/api/v1/projects/{project['id']}").status_code == 404


def test_project_membership_does_not_grant_organization_access(alice_and_bob):
    alice, bob, a, _, project = alice_and_bob
    alice.post(f"/api/v1/projects/{project['id']}/members", json={"email": "bob@example.com", "role": "editor"})
    assert bob.get(f"/api/v1/projects/{project['id']}").json()["my_role"] == "editor"
    org_id = a["organizations"][0]["id"]
    assert bob.get(f"/api/v1/organizations/{org_id}").status_code == 404
    assert bob.get(f"/api/v1/organizations/{org_id}/members").status_code == 404
    assert bob.post("/api/v1/projects", json={"name": "x", "organization_id": org_id}).status_code == 404


def test_users_cannot_see_other_users_organizations(alice_and_bob):
    _, bob, a, _, _ = alice_and_bob
    assert all(o["id"] != a["organizations"][0]["id"] for o in bob.get("/api/v1/organizations").json())


def test_access_survives_logout_and_login(alice_and_bob, make_client):
    alice, _, _, _, project = alice_and_bob
    alice.post("/api/v1/auth/logout")
    assert alice.get(f"/api/v1/projects/{project['id']}").status_code == 401
    again = make_client()
    again.post("/api/v1/auth/login", json={"email": "alice@example.com", "password": "correct horse battery"})
    assert again.get(f"/api/v1/projects/{project['id']}").json()["name"] == "Alice secret board"


def test_malformed_ids_are_validation_errors_not_crashes(alice_and_bob):
    alice, _, _, _, _ = alice_and_bob
    resp = alice.get("/api/v1/projects/not-a-uuid")
    assert resp.status_code == 422 and resp.json()["error"]["code"] == "validation_error"


def test_sql_metacharacters_in_search_are_harmless(alice_and_bob, db):
    alice, _, _, _, _ = alice_and_bob
    resp = alice.get("/api/v1/projects", params={"q": "'; DROP TABLE projects; --"})
    assert resp.status_code == 200 and resp.json()["total"] == 0
    assert db.scalar(select(User).where(User.email == "alice@example.com")) is not None
