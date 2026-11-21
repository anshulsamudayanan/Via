"""AI status, consent and the consent-gated project context."""

from __future__ import annotations

from pathlib import Path

import pytest

from tests.integration.conftest import register
from via_ai import ContextPurpose
from via_api.ai.context import ConsentRequiredError, DatabaseContextProvider
from via_api.errors import APIError

REF = (Path(__file__).resolve().parents[1] / "engineering" / "fixtures" / "via_reference_v8.kicad_pcb").read_bytes()


@pytest.fixture
def parsed(make_client):
    owner, outsider, viewer = make_client(), make_client(), make_client()
    o = register(owner, "owner@example.com")
    out = register(outsider, "out@example.com")
    v = register(viewer, "viewer@example.com")
    project = owner.post("/api/v1/projects", json={"name": "AI"}).json()
    owner.post(f"/api/v1/projects/{project['id']}/members", json={"email": "viewer@example.com"})
    design = owner.post(
        "/api/v1/pcb/import",
        data={"project_id": project["id"]},
        files={"file": ("board.kicad_pcb", REF, "application/octet-stream")},
    ).json()["design"]
    return {
        "owner": owner,
        "outsider": outsider,
        "viewer": viewer,
        "project": project,
        "design": design,
        "ids": {"owner": o["user"]["id"], "outsider": out["user"]["id"], "viewer": v["user"]["id"]},
    }


def test_status_reports_ai_disabled_by_default(client):
    register(client, "s@example.com")
    assert client.get("/api/v1/ai/status").json() == {
        "enabled": False,
        "provider": "none",
        "text": False,
        "structured_output": False,
        "embeddings": False,
        "external": False,
        "default_model": None,
    }


def test_consent_is_off_by_default_owner_only_and_revocable(parsed):
    pid = parsed["project"]["id"]
    owner, viewer, outsider = parsed["owner"], parsed["viewer"], parsed["outsider"]
    assert owner.get(f"/api/v1/ai/consent/{pid}").json()["granted"] is False
    assert viewer.put(f"/api/v1/ai/consent/{pid}").status_code == 403
    assert outsider.get(f"/api/v1/ai/consent/{pid}").status_code == 404
    granted = owner.put(f"/api/v1/ai/consent/{pid}").json()
    assert granted["granted"] is True and granted["policy_version"] == "2026-11-v1"
    assert viewer.get(f"/api/v1/ai/consent/{pid}").json()["granted"] is True
    assert owner.put(f"/api/v1/ai/consent/{pid}").status_code == 200  # idempotent
    assert owner.delete(f"/api/v1/ai/consent/{pid}").status_code == 204
    assert owner.get(f"/api/v1/ai/consent/{pid}").json()["granted"] is False
    actions = [a["action"] for a in owner.get(f"/api/v1/activity?project_id={pid}").json()["items"]]
    assert "consent.granted" in actions and "consent.revoked" in actions


def test_context_requires_access(parsed, db):
    provider = DatabaseContextProvider(db)
    with pytest.raises(APIError) as info:
        provider.build(
            user_id=parsed["ids"]["outsider"],
            design_id=parsed["design"]["id"],
            purpose=ContextPurpose.DESIGN_REVIEW,
            external=False,
        )
    assert info.value.status_code == 404


def test_external_context_requires_consent(parsed, db):
    provider = DatabaseContextProvider(db)
    args = {
        "user_id": parsed["ids"]["viewer"],
        "design_id": parsed["design"]["id"],
        "purpose": ContextPurpose.DESIGN_REVIEW,
    }
    with pytest.raises(ConsentRequiredError):
        provider.build(**args, external=True)
    parsed["owner"].put(f"/api/v1/ai/consent/{parsed['project']['id']}")
    ctx = provider.build(**args, external=True)
    assert ctx.design_name == "board"
    # Revocation takes effect immediately.
    parsed["owner"].delete(f"/api/v1/ai/consent/{parsed['project']['id']}")
    with pytest.raises(ConsentRequiredError):
        provider.build(**args, external=True)


def test_context_contains_only_summary_data(parsed, db):
    ctx = DatabaseContextProvider(db).build(
        user_id=parsed["ids"]["owner"],
        design_id=parsed["design"]["id"],
        purpose=ContextPurpose.DESIGN_REVIEW,
        external=False,
    )
    assert ctx.revision_number == 1 and ctx.source_format == "kicad"
    assert ctx.stats["component_count"] == 4
    assert [c.reference for c in ctx.components] == ["C1", "H1", "J1", "R1"]
    assert ctx.net_names == ["GND", "SIG", "VCC"]
    assert [layer.name for layer in ctx.layers][:2] == ["F.Cu", "B.Cu"]
    assert ctx.truncated == {}
    dumped = ctx.model_dump_json()
    # No source file content, storage keys, emails or hashes of the upload.
    assert "kicad_pcb (version" not in dumped and "projects/" not in dumped and "@example.com" not in dumped
    assert parsed["design"]["latest_revision"]["source_sha256"] not in dumped
