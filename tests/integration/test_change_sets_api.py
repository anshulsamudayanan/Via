# ruff: noqa: E501  (test data)
"""Change sets: create from candidates or user changes, apply (patch + verify + import), roll back, compare.

The export job runs inline with the real sandboxed exporter, so these tests exercise the full path from
an accepted candidate to a downloadable patched file and a new revision.
"""

from __future__ import annotations

import pytest
from sqlalchemy import select

from tests.engineering.synthetic import Board
from tests.integration.conftest import register
from via_api.models import ActivityLog
from via_pcb.adapters.kicad import KiCadAdapter


def board() -> bytes:
    b = Board().footprint("R1", 5, 5, [{"net": "A"}]).footprint("R2", 15, 5, [{"net": "A"}])
    b.track((5, 5), (15, 5), 0.1, "A")
    return b.bytes()


@pytest.fixture
def setup(client):
    register(client, "changes@example.com")
    project = client.post("/api/v1/projects", json={"name": "Changes"}).json()
    design = client.post("/api/v1/pcb/import", data={"project_id": project["id"]},
                         files={"file": ("s.kicad_pcb", board(), "application/octet-stream")}).json()["design"]  # fmt: skip
    return project, design


def components(client, design_id):
    """Components of the current revision by reference, with their stable model ids."""
    norm = client.get(f"/api/v1/pcb/{design_id}/normalized").json()
    return {c["reference"]: {**c, "x": c["position"]["x"]} for c in norm["components"]}


def accepted_outline_candidate(client, design_id):
    run = client.post(f"/api/v1/designs/{design_id}/optimization-runs", json={"objectives": ["area"]}).json()
    cand = next(
        c for c in client.get(f"/api/v1/optimization-runs/{run['id']}/candidates").json() if c["key"] == "outline_fit"
    )
    assert (
        client.post(f"/api/v1/optimization-candidates/{cand['id']}/decision", json={"status": "accepted"}).status_code
        == 200
    )
    return cand


def test_apply_candidate_creates_child_revision_and_patched_file(client, setup, db):
    _, design = setup
    base_rev = client.get(f"/api/v1/designs/{design['id']}").json()["current_revision"]
    cand = accepted_outline_candidate(client, design["id"])
    cs = client.post(
        f"/api/v1/designs/{design['id']}/change-sets", json={"candidate_ids": [cand["id"]], "title": "Shrink"}
    )
    assert cs.status_code == 201, cs.text
    cs = cs.json()
    assert cs["status"] == "draft" and cs["changes"][0]["origin_candidate_id"] == cand["id"]
    preview = client.get(f"/api/v1/change-sets/{cs['id']}/preview").json()
    assert preview["source"] == "simulated" and preview["deltas"]["board_area_mm2"] < 0

    applied = client.post(f"/api/v1/change-sets/{cs['id']}/apply")
    assert applied.status_code == 202, applied.text
    cs = client.get(f"/api/v1/change-sets/{cs['id']}").json()
    assert cs["status"] == "applied", cs
    assert all(c["status"] == "applied" for c in cs["changes"])
    detail = client.get(f"/api/v1/designs/{design['id']}").json()
    assert detail["current_revision"]["id"] == cs["result_revision_id"] != base_rev["id"]

    # The downloaded file is the original with only the outline replaced.
    resp = client.get(f"/api/v1/change-sets/{cs['id']}/download")
    assert resp.status_code == 200 and "-via-r2" in resp.headers["content-disposition"]
    exported = KiCadAdapter().parse(resp.content, filename="x.kicad_pcb")
    after = cs["changes"][0]["after"]
    bb = exported.outline.bbox
    assert (bb.min_x, bb.min_y, bb.max_x, bb.max_y) == pytest.approx(
        (after["min_x"], after["min_y"], after["max_x"], after["max_y"])
    )
    assert [c.reference for c in exported.components] == ["R1", "R2"]

    lineage = client.get(f"/api/v1/designs/{design['id']}/lineage").json()
    child = next(r for r in lineage if r["revision_id"] == cs["result_revision_id"])
    assert child["parent_revision_id"] == base_rev["id"] and child["change_set_id"] == cs["id"]
    actions = set(db.scalars(select(ActivityLog.action)).all())
    assert {"change_set.created", "change_set.apply_requested", "change_set.applied"} <= actions

    # Rollback makes the base current again; nothing is deleted.
    rb = client.post(f"/api/v1/change-sets/{cs['id']}/rollback").json()
    assert rb["status"] == "rolled_back"
    detail = client.get(f"/api/v1/designs/{design['id']}").json()
    assert detail["current_revision"]["id"] == base_rev["id"] and detail["revision_count"] == 2
    assert client.post(f"/api/v1/change-sets/{cs['id']}/rollback").status_code == 409


def test_user_changes_move_rotate_and_width(client, setup):
    _, design = setup
    comps = components(client, design["id"])
    norm = client.get(f"/api/v1/pcb/{design['id']}/normalized").json()
    track = norm["tracks"][0]
    body = {"changes": [
        {"kind": "move_component", "target": {"kind": "component", "id": comps["R2"]["id"], "label": "R2"}, "after": {"x": 18, "y": 5}},
        {"kind": "rotate_component", "target": {"kind": "component", "id": comps["R1"]["id"], "label": "R1"}, "after": {"rotation": 90}},
        {"kind": "set_track_width", "target": {"kind": "track", "id": track["id"]}, "after": {"width": 0.25}},
    ]}  # fmt: skip
    cs = client.post(f"/api/v1/designs/{design['id']}/change-sets", json=body)
    assert cs.status_code == 201, cs.text
    cs = cs.json()
    assert cs["changes"][0]["before"] == {"x": 15, "y": 5} and all(c["source"] == "user" for c in cs["changes"])
    client.post(f"/api/v1/change-sets/{cs['id']}/apply")
    cs = client.get(f"/api/v1/change-sets/{cs['id']}").json()
    assert cs["status"] == "applied", cs
    exported = KiCadAdapter().parse(
        client.get(f"/api/v1/change-sets/{cs['id']}/download").content, filename="x.kicad_pcb"
    )
    by_ref = {c.reference: c for c in exported.components}
    assert (by_ref["R2"].position.x, by_ref["R2"].position.y) == (18, 5) and by_ref["R1"].rotation == 90
    assert exported.tracks[0].width == 0.25
    # Components of the new current revision come from the re-imported file.
    assert components(client, design["id"])["R2"]["x"] == 18


def test_validation_conflicts_and_undo(client, setup):
    _, design = setup
    comps = components(client, design["id"])
    r1 = {"kind": "component", "id": comps["R1"]["id"]}
    url = f"/api/v1/designs/{design['id']}/change-sets"
    conflict = client.post(url, json={"changes": [
        {"kind": "move_component", "target": r1, "after": {"x": 1, "y": 1}},
        {"kind": "rotate_component", "target": r1, "after": {"rotation": 90}},
    ]})  # fmt: skip
    assert conflict.status_code == 409 and conflict.json()["error"]["code"] == "conflicting_changes"
    assert (
        client.post(
            url,
            json={
                "changes": [
                    {
                        "kind": "move_component",
                        "target": {"kind": "component", "id": "component:nope"},
                        "after": {"x": 1, "y": 1},
                    }
                ]
            },
        ).status_code
        == 422
    )
    assert (
        client.post(
            url,
            json={
                "changes": [
                    {
                        "kind": "set_copper_layer_count",
                        "target": {"kind": "stackup", "id": "stackup"},
                        "after": {"count": 2},
                    }
                ]
            },
        ).json()["error"]["code"]
        == "not_exportable"
    )
    assert (
        client.post(
            url,
            json={
                "changes": [
                    {
                        "kind": "set_via_size",
                        "target": {"kind": "via", "id": "v"},
                        "after": {"diameter": 0.3, "drill": 0.4},
                    }
                ]
            },
        ).status_code
        == 422
    )
    assert client.post(url, json={}).json()["error"]["code"] == "empty_change_set"

    cs = client.post(url, json={"changes": [
        {"kind": "move_component", "target": r1, "after": {"x": 6, "y": 5}},
        {"kind": "move_component", "target": {"kind": "component", "id": comps["R2"]["id"]}, "after": {"x": 16, "y": 5}},
    ]}).json()  # fmt: skip
    assert client.delete(f"/api/v1/change-sets/{cs['id']}/changes/{cs['changes'][0]['id']}").status_code == 204
    assert [c["ordinal"] for c in client.get(f"/api/v1/change-sets/{cs['id']}").json()["changes"]] == [1]
    assert client.delete(f"/api/v1/change-sets/{cs['id']}").status_code == 204
    assert client.get(f"/api/v1/change-sets/{cs['id']}").status_code == 404


def test_unaccepted_and_outdated_candidates_are_refused(client, setup):
    _, design = setup
    run = client.post(f"/api/v1/designs/{design['id']}/optimization-runs", json={"objectives": ["area"]}).json()
    cand = client.get(f"/api/v1/optimization-runs/{run['id']}/candidates").json()[0]
    url = f"/api/v1/designs/{design['id']}/change-sets"
    assert client.post(url, json={"candidate_ids": [cand["id"]]}).json()["error"]["code"] == "candidate_not_accepted"
    client.post(f"/api/v1/optimization-candidates/{cand['id']}/decision", json={"status": "accepted"})
    cs = client.post(url, json={"candidate_ids": [cand["id"]]}).json()
    client.post(f"/api/v1/change-sets/{cs['id']}/apply")
    # The design moved on: the old candidate no longer applies, and the applied set can't be edited.
    assert client.post(url, json={"candidate_ids": [cand["id"]]}).json()["error"]["code"] == "candidate_outdated"
    assert client.delete(f"/api/v1/change-sets/{cs['id']}").status_code == 409


def test_stale_base_cannot_be_applied(client, setup):
    _, design = setup
    comps = components(client, design["id"])
    url = f"/api/v1/designs/{design['id']}/change-sets"
    first = client.post(
        url,
        json={
            "changes": [
                {
                    "kind": "move_component",
                    "target": {"kind": "component", "id": comps["R1"]["id"]},
                    "after": {"x": 6, "y": 5},
                }
            ]
        },
    ).json()
    second = client.post(
        url,
        json={
            "changes": [
                {
                    "kind": "move_component",
                    "target": {"kind": "component", "id": comps["R2"]["id"]},
                    "after": {"x": 16, "y": 5},
                }
            ]
        },
    ).json()
    client.post(f"/api/v1/change-sets/{first['id']}/apply")
    resp = client.post(f"/api/v1/change-sets/{second['id']}/apply")
    assert resp.status_code == 409 and resp.json()["error"]["code"] == "base_not_current"


def test_follow_up_analysis_and_comparison(client, setup):
    _, design = setup
    base = client.get(f"/api/v1/designs/{design['id']}").json()["current_revision"]
    client.post(f"/api/v1/designs/{design['id']}/analysis-runs", json={"checks": ["mfg_track_width"]})
    norm = client.get(f"/api/v1/pcb/{design['id']}/normalized").json()
    cs = client.post(f"/api/v1/designs/{design['id']}/change-sets", json={"changes": [
        {"kind": "set_track_width", "target": {"kind": "track", "id": norm["tracks"][0]["id"]}, "after": {"width": 0.3}}]}).json()  # fmt: skip
    client.post(f"/api/v1/change-sets/{cs['id']}/apply")
    cs = client.get(f"/api/v1/change-sets/{cs['id']}").json()
    assert cs["status"] == "applied" and cs["result"]["follow_up_analysis_run_id"]
    cmp_ = client.get(
        f"/api/v1/designs/{design['id']}/compare", params={"base": base["id"], "head": cs["result_revision_id"]}
    ).json()
    assert cmp_["findings"]["base_total"] == 1 and cmp_["findings"]["head_total"] == 0
    assert len(cmp_["findings"]["resolved"]) == 1 and cmp_["findings"]["resolved"][0]["rule"] == "track_too_narrow"
    assert cmp_["findings"]["introduced"] == []


def test_viewers_can_read_but_not_change(client, make_client, setup):
    project, design = setup
    comps = components(client, design["id"])
    cs = client.post(f"/api/v1/designs/{design['id']}/change-sets", json={"changes": [
        {"kind": "move_component", "target": {"kind": "component", "id": comps["R1"]["id"]}, "after": {"x": 6, "y": 5}}]}).json()  # fmt: skip
    viewer = make_client()
    register(viewer, "cs-viewer@example.com")
    client.post(f"/api/v1/projects/{project['id']}/members", json={"email": "cs-viewer@example.com", "role": "viewer"})
    assert viewer.get(f"/api/v1/change-sets/{cs['id']}").status_code == 200
    assert viewer.post(f"/api/v1/change-sets/{cs['id']}/apply").status_code == 403
    assert viewer.post(f"/api/v1/designs/{design['id']}/change-sets", json={"changes": []}).status_code == 403
    outsider = make_client()
    register(outsider, "cs-outsider@example.com")
    assert outsider.get(f"/api/v1/change-sets/{cs['id']}").status_code == 404
