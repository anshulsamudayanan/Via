# ruff: noqa: E501  (test data)
"""Failure modes: storage outages and AI provider failures end in clear, honest states.

Nothing is left "running", nothing half-written is presented as a result, and the user gets a
safe message with a stable error code.
"""

from __future__ import annotations

import pytest
from sqlalchemy import func, select

from tests.engineering.synthetic import Board
from tests.integration.conftest import register
from via_ai.providers.base import AIRefusedError, AIUnavailableError
from via_ai.providers.scripted import ScriptedProvider
from via_api.ai import get_ai_provider
from via_api.models import AIOutput, RecommendationRow
from via_api.storage import StorageError
from via_api.storage.local import LocalStorage


def board() -> bytes:
    b = Board().footprint("R1", 5, 5, [{"net": "A"}]).footprint("R2", 15, 5, [{"net": "A"}])
    b.track((5, 5), (15, 5), 0.1, "A")
    return b.bytes()


@pytest.fixture
def design(client):
    register(client, "failures@example.com")
    project = client.post("/api/v1/projects", json={"name": "Failures"}).json()
    imported = client.post("/api/v1/pcb/import", data={"project_id": project["id"]},
                           files={"file": ("s.kicad_pcb", board(), "application/octet-stream")}).json()  # fmt: skip
    return project, imported["design"]


def broken(monkeypatch, method: str) -> None:
    def fail(self, *a, **kw):
        raise StorageError("storage is down")

    monkeypatch.setattr(LocalStorage, method, fail)


def test_upload_during_a_storage_outage_is_refused_cleanly(client, design, monkeypatch):
    project, _ = design
    broken(monkeypatch, "put")
    other = board() + b"\n"  # different bytes, so not a duplicate
    resp = client.post("/api/v1/pcb/import", data={"project_id": project["id"]},
                       files={"file": ("t.kicad_pcb", other, "application/octet-stream")})  # fmt: skip
    assert resp.status_code == 503 and resp.json()["error"]["code"] == "storage_unavailable"
    designs = client.get("/api/v1/designs", params={"project_id": project["id"]}).json()
    assert len(designs) == 1  # no half-created design or revision was kept


def test_analysis_fails_with_a_reason_when_the_design_cannot_be_read(client, design, monkeypatch):
    _, d = design
    broken(monkeypatch, "get")
    run = client.post(f"/api/v1/designs/{d['id']}/analysis-runs", json={"checks": ["board_outline"]}).json()
    run = client.get(f"/api/v1/analysis-runs/{run['id']}").json()
    assert run["status"] == "failed" and run["error_code"] == "design_unavailable"
    assert client.get(f"/api/v1/analysis-runs/{run['id']}/findings").json()["total"] == 0


def test_export_fails_with_a_reason_and_can_be_retried(client, design, monkeypatch):
    _, d = design
    comp = client.get(f"/api/v1/pcb/{d['id']}/normalized").json()["components"][0]
    cs = client.post(f"/api/v1/designs/{d['id']}/change-sets", json={"changes": [
        {"kind": "move_component", "target": {"kind": "component", "id": comp["id"]}, "after": {"x": 6, "y": 5}}]}).json()  # fmt: skip
    with monkeypatch.context() as m:
        broken(m, "get")
        client.post(f"/api/v1/change-sets/{cs['id']}/apply")
    failed = client.get(f"/api/v1/change-sets/{cs['id']}").json()
    assert failed["status"] == "failed" and failed["error_code"] == "storage_unavailable"
    assert client.get(f"/api/v1/designs/{d['id']}").json()["revision_count"] == 1  # nothing half-applied
    # Storage is back: the same change set applies.
    assert client.post(f"/api/v1/change-sets/{cs['id']}/apply").status_code == 202
    assert client.get(f"/api/v1/change-sets/{cs['id']}").json()["status"] == "applied"


@pytest.fixture
def provider(app):
    def install(*outputs):
        p = ScriptedProvider(list(outputs))
        app.dependency_overrides[get_ai_provider] = lambda: p
        return p

    yield install
    app.dependency_overrides.pop(get_ai_provider, None)


def test_ai_provider_outage_and_refusal_are_reported_not_hidden(client, design, provider, db):
    _, d = design
    provider(AIUnavailableError("upstream timed out"), AIRefusedError("no"), AIUnavailableError("down"))
    down = client.post(f"/api/v1/designs/{d['id']}/ai/explain", json={"question": "Why?"})
    assert down.status_code == 503 and down.json()["error"]["code"] == "ai_unavailable"
    refused = client.post(f"/api/v1/designs/{d['id']}/ai/explain", json={"question": "Why?"})
    assert refused.status_code == 422 and refused.json()["error"]["code"] == "ai_refused"
    review = client.post(f"/api/v1/designs/{d['id']}/ai/review", json={})
    assert review.status_code == 503
    # No answer, no recommendation was invented in place of the failed calls.
    assert db.scalar(select(func.count(AIOutput.id))) == 0
    assert db.scalar(select(func.count(RecommendationRow.id))) == 0


def test_an_unexpected_error_inside_the_ai_call_is_a_503_with_a_cause_not_a_bare_500(client, design, provider):
    _, d = design
    provider(ValueError("boom"))
    r = client.post(f"/api/v1/designs/{d['id']}/ai/explain", json={"question": "Why?"})
    assert r.status_code == 503 and r.json()["error"]["code"] == "ai_unavailable"
    assert "ValueError" in r.json()["error"]["message"]
