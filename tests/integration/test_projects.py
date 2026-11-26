"""Projects: creation, editing, archive, delete, search/filter, members, activity."""

from __future__ import annotations

from sqlalchemy import select

from tests.integration.conftest import register
from via_api.models import ActivityLog, ProjectMembership


def create(client, name="Motor Controller", **extra) -> dict:
    resp = client.post("/api/v1/projects", json={"name": name, **extra})
    assert resp.status_code == 201, resp.json()
    return resp.json()


def test_create_project_defaults(client, db):
    me = register(client, "owner@example.com", "Olive Owner")
    project = create(client, description="  BLDC driver  ")
    assert project["visibility"] == "private"
    assert project["my_role"] == "owner"
    assert project["description"] == "BLDC driver"
    assert project["design_count"] == 0
    assert project["owner"]["display_name"] == "Olive Owner"
    assert project["organization"]["id"] == me["organizations"][0]["id"]
    assert project["organization"]["is_personal"] is True
    owner_row = db.scalar(select(ProjectMembership).where(ProjectMembership.project_id == project["id"]))
    assert owner_row.role == "owner"


def test_create_validation(client):
    register(client, "v@example.com")
    assert client.post("/api/v1/projects", json={"name": ""}).status_code == 422
    assert client.post("/api/v1/projects", json={"name": "x" * 121}).status_code == 422
    assert client.post("/api/v1/projects", json={"name": "ok", "description": "d" * 2001}).status_code == 422
    assert client.post("/api/v1/projects", json={"name": "ok", "visibility": "public"}).status_code == 422


def test_cannot_create_in_an_organization_you_dont_belong_to(client, make_client):
    other = make_client()
    other_org = register(other, "other@example.com")["organizations"][0]["id"]
    register(client, "me@example.com")
    resp = client.post("/api/v1/projects", json={"name": "Sneaky", "organization_id": other_org})
    assert resp.status_code == 404


def test_rename_edit_description_and_activity(client, db):
    register(client, "e@example.com")
    p = create(client, "Old")
    resp = client.patch(f"/api/v1/projects/{p['id']}", json={"name": "New", "description": "Updated"})
    assert resp.status_code == 200
    assert (resp.json()["name"], resp.json()["description"]) == ("New", "Updated")
    log = db.scalar(select(ActivityLog).where(ActivityLog.action == "project.updated"))
    assert log.details["changes"]["name"] == {"from": "Old", "to": "New"}
    assert log.details["changes"]["description"] is True  # flagged, content not duplicated
    # No-op updates don't create activity.
    client.patch(f"/api/v1/projects/{p['id']}", json={"name": "New"})
    assert len(db.scalars(select(ActivityLog).where(ActivityLog.action == "project.updated")).all()) == 1


def test_archive_and_unarchive(client):
    register(client, "a@example.com")
    p = create(client)
    archived = client.post(f"/api/v1/projects/{p['id']}/archive").json()
    assert archived["archived_at"] is not None
    edit = client.patch(f"/api/v1/projects/{p['id']}", json={"name": "Nope"})
    assert edit.status_code == 409 and edit.json()["error"]["code"] == "project_archived"
    assert client.get("/api/v1/projects").json()["total"] == 0  # default filter: active
    assert client.get("/api/v1/projects?status=archived").json()["total"] == 1
    assert client.get("/api/v1/projects/summary").json() == {
        "active": 0,
        "archived": 1,
        "designs": 0,
        "imports_7d": 0,
        "analyses_7d": 0,
    }
    restored = client.post(f"/api/v1/projects/{p['id']}/unarchive").json()
    assert restored["archived_at"] is None
    assert client.patch(f"/api/v1/projects/{p['id']}", json={"name": "Yes"}).status_code == 200


def test_delete_project(client, db):
    register(client, "d@example.com")
    p = create(client, "Doomed")
    assert client.delete(f"/api/v1/projects/{p['id']}").status_code == 204
    assert client.get(f"/api/v1/projects/{p['id']}").status_code == 404
    assert db.scalar(select(ProjectMembership).where(ProjectMembership.project_id == p["id"])) is None
    log = db.scalar(select(ActivityLog).where(ActivityLog.action == "project.deleted"))
    assert log.details == {"name": "Doomed"} and log.project_id is None
    # The deleting user still sees the deletion in their own feed.
    actions = [a["action"] for a in client.get("/api/v1/activity").json()["items"]]
    assert "project.deleted" in actions


def test_search_filter_sort_and_pagination(client):
    register(client, "s@example.com")
    for name, desc in [("Alpha board", ""), ("beta sensor", "uses an alpha chip"), ("Gamma", ""), ("100% test", "")]:
        create(client, name, description=desc)
    names = lambda r: [p["name"] for p in r.json()["items"]]  # noqa: E731
    assert names(client.get("/api/v1/projects?q=ALPHA&sort=name")) == ["Alpha board", "beta sensor"]
    assert names(client.get("/api/v1/projects?q=%25")) == ["100% test"]  # LIKE wildcards are escaped
    assert client.get("/api/v1/projects?q=_").json()["total"] == 0
    page1 = client.get("/api/v1/projects?sort=name&limit=2&offset=0").json()
    page2 = client.get("/api/v1/projects?sort=name&limit=2&offset=2").json()
    assert page1["total"] == page2["total"] == 4
    assert [p["name"] for p in page1["items"] + page2["items"]] == ["100% test", "Alpha board", "beta sensor", "Gamma"]
    assert client.get("/api/v1/projects?limit=101").status_code == 422
    assert client.get("/api/v1/projects?status=deleted").status_code == 422


def test_members_lifecycle_and_roles(client, make_client):
    register(client, "owner@example.com")
    editor, viewer = make_client(), make_client()
    editor_id = register(editor, "editor@example.com", "Ed")["user"]["id"]
    viewer_id = register(viewer, "viewer@example.com", "Vi")["user"]["id"]
    p = create(client)
    pid = p["id"]

    assert (
        client.post(
            f"/api/v1/projects/{pid}/members", json={"email": "EDITOR@example.com", "role": "editor"}
        ).status_code
        == 201
    )
    assert (
        client.post(f"/api/v1/projects/{pid}/members", json={"email": "viewer@example.com"}).json()["role"] == "viewer"
    )
    assert client.post(f"/api/v1/projects/{pid}/members", json={"email": "viewer@example.com"}).status_code == 409
    unknown = client.post(f"/api/v1/projects/{pid}/members", json={"email": "ghost@example.com"})
    assert unknown.status_code == 404 and unknown.json()["error"]["code"] == "user_not_found"
    assert (
        client.post(
            f"/api/v1/projects/{pid}/members", json={"email": "editor@example.com", "role": "owner"}
        ).status_code
        == 422
    )

    members = client.get(f"/api/v1/projects/{pid}/members").json()
    assert sorted(m["role"] for m in members) == ["editor", "owner", "viewer"]

    # Editor: can rename, can't change visibility, archive, delete or manage members.
    assert editor.get(f"/api/v1/projects/{pid}").json()["my_role"] == "editor"
    assert editor.patch(f"/api/v1/projects/{pid}", json={"name": "Edited"}).status_code == 200
    assert editor.patch(f"/api/v1/projects/{pid}", json={"visibility": "organization"}).status_code == 403
    assert editor.post(f"/api/v1/projects/{pid}/archive").status_code == 403
    assert editor.delete(f"/api/v1/projects/{pid}").status_code == 403
    assert editor.post(f"/api/v1/projects/{pid}/members", json={"email": "owner@example.com"}).status_code == 403

    # Viewer: read-only.
    assert viewer.get(f"/api/v1/projects/{pid}").status_code == 200
    assert viewer.get(f"/api/v1/projects/{pid}/members").status_code == 200
    forbidden = viewer.patch(f"/api/v1/projects/{pid}", json={"name": "Hacked"})
    assert forbidden.status_code == 403 and forbidden.json()["error"]["code"] == "forbidden"

    # Owner promotes viewer, can't demote/remove themselves.
    owner_id = p["owner"]["id"]
    assert (
        client.patch(f"/api/v1/projects/{pid}/members/{viewer_id}", json={"role": "editor"}).json()["role"] == "editor"
    )
    assert client.patch(f"/api/v1/projects/{pid}/members/{owner_id}", json={"role": "viewer"}).status_code == 422
    assert client.delete(f"/api/v1/projects/{pid}/members/{owner_id}").status_code == 422

    # Members can leave; removed members lose access.
    assert editor.delete(f"/api/v1/projects/{pid}/members/{editor_id}").status_code == 204
    assert editor.get(f"/api/v1/projects/{pid}").status_code == 404
    assert client.delete(f"/api/v1/projects/{pid}/members/{viewer_id}").status_code == 204
    assert viewer.get(f"/api/v1/projects/{pid}").status_code == 404


def test_project_activity_feed(client, make_client):
    register(client, "feed@example.com")
    p = create(client, "Feed")
    client.patch(f"/api/v1/projects/{p['id']}", json={"name": "Feed 2"})
    feed = client.get(f"/api/v1/activity?project_id={p['id']}").json()
    assert [i["action"] for i in feed["items"]] == ["project.updated", "project.created"]
    item = feed["items"][0]
    assert item["project"] == {"id": p["id"], "name": "Feed 2"}
    assert item["actor"]["display_name"] == "Test User"
    assert "ip_address" not in item and "user_agent" not in item


def test_create_team_organization(client):
    register(client, "team@example.com")
    org = client.post("/api/v1/organizations", json={"name": "Acme Hardware"}).json()
    assert org["is_personal"] is False and org["role"] == "owner"
    assert org["slug"].startswith("acme-hardware-")
    assert len(client.get("/api/v1/organizations").json()) == 2
    p = create(client, "Team board", organization_id=org["id"])
    assert p["organization"]["name"] == "Acme Hardware"
    assert client.get(f"/api/v1/projects?organization_id={org['id']}").json()["total"] == 1
