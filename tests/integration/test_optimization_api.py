# ruff: noqa: E501  (test data)
"""VIA Optimize through the API with the worker logic running inline."""

from __future__ import annotations

import pytest

from tests.engineering.synthetic import Board
from tests.integration.conftest import register


def board() -> bytes:
    # Outline 0..40 x 0..30, parts only in the top-left: the outline can shrink. A 0.1 mm track is below the profile.
    b = Board().footprint("R1", 5, 5, [{"net": "A"}]).footprint("R2", 15, 5, [{"net": "A"}])
    b.track((5, 5), (15, 5), 0.1, "A")
    return b.bytes()


@pytest.fixture
def design(client):
    register(client, "opt@example.com")
    project = client.post("/api/v1/projects", json={"name": "Optimize"}).json()
    return client.post("/api/v1/pcb/import", data={"project_id": project["id"]},
                       files={"file": ("s.kicad_pcb", board(), "application/octet-stream")}).json()["design"]  # fmt: skip


def start(client, design_id, **body):
    return client.post(f"/api/v1/designs/{design_id}/optimization-runs", json=body)


def test_run_generates_validated_candidates_without_touching_the_design(client, design):
    revisions_before = client.get(f"/api/v1/designs/{design['id']}").json()["revision_count"]
    resp = start(client, design["id"], objectives=["area", "manufacturability"])
    assert resp.status_code == 202, resp.text
    run = client.get(f"/api/v1/optimization-runs/{resp.json()['id']}").json()
    assert run["status"] == "succeeded" and run["optimizer_version"]
    assert run["config"]["options"]["manufacturing_profile"]["key"] == "via-conservative"
    cands = {c["key"]: c for c in client.get(f"/api/v1/optimization-runs/{run['id']}/candidates").json()}
    assert set(cands) == {"outline_fit", "track_min_width"}
    assert all(c["status"] == "validated" for c in cands.values())
    detail = client.get(f"/api/v1/optimization-candidates/{cands['outline_fit']['id']}").json()
    (change,) = detail["changes"]
    assert change["kind"] == "set_outline_rect" and change["exportable"] and change["before"]["max_x"] == 40
    assert client.get(f"/api/v1/designs/{design['id']}").json()["revision_count"] == revisions_before  # never applied


def test_compare_and_pareto(client, design):
    run = start(client, design["id"], objectives=["area", "manufacturability"]).json()
    cmp_ = client.get(f"/api/v1/optimization-runs/{run['id']}/compare").json()
    assert cmp_["objectives"] == ["area", "manufacturability"]
    rows = {r["key"]: r for r in cmp_["rows"]}
    assert rows["outline_fit"]["deltas"]["board_area_mm2"] < 0
    assert rows["track_min_width"]["deltas"]["manufacturing_issues"] < 0
    # Neither beats the other on both objectives: both are on the Pareto front.
    assert len(cmp_["pareto"]) == 2


def test_decisions(client, design):
    run = start(client, design["id"], objectives=["area", "placement"]).json()
    cands = {c["key"]: c for c in client.get(f"/api/v1/optimization-runs/{run['id']}/candidates").json()}
    accepted = client.post(
        f"/api/v1/optimization-candidates/{cands['outline_fit']['id']}/decision", json={"status": "accepted"}
    ).json()
    assert accepted["status"] == "accepted"
    if "placement_ratsnest" in cands:  # moves routed parts: awaiting validation, can't be accepted
        resp = client.post(
            f"/api/v1/optimization-candidates/{cands['placement_ratsnest']['id']}/decision", json={"status": "accepted"}
        )
        assert resp.status_code == 409 and resp.json()["error"]["code"] == "not_validated"
    no_reason = client.post(
        f"/api/v1/optimization-candidates/{cands['outline_fit']['id']}/decision", json={"status": "rejected"}
    )
    assert no_reason.status_code == 422


def test_constraints_and_inputs_are_recorded(client, design):
    run = start(client, design["id"], objectives=["area"], constraints={"outline_fixed": True}).json()
    run = client.get(f"/api/v1/optimization-runs/{run['id']}").json()
    assert run["config"]["constraints"]["outline_fixed"] is True
    assert client.get(f"/api/v1/optimization-runs/{run['id']}/candidates").json() == []
    assert any("fixed" in n for n in run["summary"]["notes"])
    assert start(client, design["id"], objectives=["teleport"]).status_code == 422
    assert start(client, design["id"], objectives=[]).status_code == 422


def test_viewers_cannot_start_or_decide(client, make_client, design):
    project_id = client.get(f"/api/v1/designs/{design['id']}").json()["project_id"]
    viewer = make_client()
    register(viewer, "optviewer@example.com")
    client.post(f"/api/v1/projects/{project_id}/members", json={"email": "optviewer@example.com", "role": "viewer"})
    run = start(client, design["id"], objectives=["area"]).json()
    assert start(viewer, design["id"], objectives=["area"]).status_code == 403
    cand = client.get(f"/api/v1/optimization-runs/{run['id']}/candidates").json()[0]
    assert viewer.get(f"/api/v1/optimization-candidates/{cand['id']}").status_code == 200
    assert (
        viewer.post(f"/api/v1/optimization-candidates/{cand['id']}/decision", json={"status": "accepted"}).status_code
        == 403
    )


def test_stale_optimization_run_is_requeued(client, design, job_queue, db, settings):
    import uuid
    from datetime import timedelta

    from via_api import jobs
    from via_api.models import AnalysisRun
    from via_api.models.base import utcnow
    from via_api.models.enums import AnalysisStatus

    job_queue.run = False
    run_id = uuid.UUID(start(client, design["id"], objectives=["area"]).json()["id"])
    run = db.get(AnalysisRun, run_id)
    run.status = AnalysisStatus.RUNNING
    run.started_at = run.heartbeat_at = utcnow() - timedelta(seconds=settings.job_stale_after_seconds + 5)
    db.commit()
    report = jobs.reap_analyses(db, job_queue, settings)
    assert report.requeued == [run_id] and job_queue.optimizations[-1] == (run_id, 2)
    assert db.get(AnalysisRun, run_id).job_id == f"optimization-{run_id}-a2"
