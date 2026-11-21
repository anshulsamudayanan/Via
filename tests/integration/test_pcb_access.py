"""Authorization for uploads and every design/PCB/file endpoint."""

from __future__ import annotations

from pathlib import Path

import pytest

from tests.integration.conftest import register

REF = (Path(__file__).resolve().parents[1] / "engineering" / "fixtures" / "via_reference_v8.kicad_pcb").read_bytes()


def upload(client, project_id, data=REF, **form):
    return client.post(
        "/api/v1/pcb/import",
        data={"project_id": project_id, **form},
        files={"file": ("board.kicad_pcb", data, "application/octet-stream")},
    )


@pytest.fixture
def setup(make_client):
    owner, outsider, viewer = make_client(), make_client(), make_client()
    register(owner, "owner@example.com")
    register(outsider, "outsider@example.com")
    register(viewer, "viewer@example.com")
    project = owner.post("/api/v1/projects", json={"name": "Private"}).json()
    owner.post(f"/api/v1/projects/{project['id']}/members", json={"email": "viewer@example.com", "role": "viewer"})
    resp = upload(owner, project["id"]).json()
    return owner, outsider, viewer, project, resp["design"], resp["revision"]


def read_endpoints(design_id, revision_id, file_id, project_id):
    return [
        f"/api/v1/designs/{design_id}",
        f"/api/v1/designs?project_id={project_id}",
        f"/api/v1/revisions/{revision_id}",
        f"/api/v1/pcb/{design_id}",
        f"/api/v1/pcb/{design_id}/normalized",
        f"/api/v1/pcb/{design_id}/components",
        f"/api/v1/pcb/{design_id}/nets",
        f"/api/v1/pcb/{design_id}/layers",
        f"/api/v1/files?project_id={project_id}",
        f"/api/v1/files/{file_id}/download",
    ]


def test_outsiders_cannot_see_anything(setup):
    owner, outsider, _, project, design, revision = setup
    file_id = revision["source_file"]["id"]
    for path in read_endpoints(design["id"], revision["id"], file_id, project["id"]):
        resp = outsider.get(path)
        assert resp.status_code == 404, (path, resp.status_code)
    assert outsider.patch(f"/api/v1/designs/{design['id']}", json={"name": "x"}).status_code == 404
    assert outsider.delete(f"/api/v1/designs/{design['id']}").status_code == 404
    assert upload(outsider, project["id"]).status_code == 404
    # Uploading into someone else's design via your own project is also refused.
    mine = outsider.post("/api/v1/projects", json={"name": "Mine"}).json()
    other = b"(kicad_pcb (version 20240108))"
    assert upload(outsider, mine["id"], data=other, design_id=design["id"]).status_code == 404
    assert owner.get(f"/api/v1/designs/{design['id']}").json()["revision_count"] == 1


def test_viewers_can_read_but_not_change(setup):
    _, _, viewer, project, design, revision = setup
    file_id = revision["source_file"]["id"]
    for path in read_endpoints(design["id"], revision["id"], file_id, project["id"]):
        assert viewer.get(path).status_code == 200, path
    assert upload(viewer, project["id"], data=b"(kicad_pcb (version 2))").status_code == 403
    assert viewer.patch(f"/api/v1/designs/{design['id']}", json={"name": "x"}).status_code == 403
    assert viewer.delete(f"/api/v1/designs/{design['id']}").status_code == 403


def test_archived_projects_reject_uploads_and_changes(setup):
    owner, _, _, project, design, _ = setup
    owner.post(f"/api/v1/projects/{project['id']}/archive")
    resp = upload(owner, project["id"], data=b"(kicad_pcb (version 3))")
    assert resp.status_code == 409 and resp.json()["error"]["code"] == "project_archived"
    assert owner.delete(f"/api/v1/designs/{design['id']}").status_code == 409
    assert owner.get(f"/api/v1/pcb/{design['id']}").status_code == 200  # still readable


def test_unauthenticated_access_is_rejected(setup, make_client):
    _, _, _, project, design, revision = setup
    anon = make_client()
    for path in read_endpoints(design["id"], revision["id"], revision["source_file"]["id"], project["id"]):
        assert anon.get(path).status_code == 401, path
    assert upload(anon, project["id"]).status_code == 401
