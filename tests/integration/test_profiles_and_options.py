"""Manufacturing profiles and analysis options through the API."""

from __future__ import annotations

from pathlib import Path

import pytest

from tests.integration.conftest import register

REF = (Path(__file__).resolve().parents[1] / "engineering" / "fixtures" / "via_reference_v8.kicad_pcb").read_bytes()
VALUES = {
    **{"min_track_width": 0.3, "min_clearance": 0.2, "min_drill": 0.3, "min_via_diameter": 0.6},
    **{"min_annular_ring": 0.15, "min_hole_to_hole": 0.5, "min_copper_to_edge": 0.3, "min_silk_width": 0.15},
}


@pytest.fixture
def setup(client):
    register(client, "profiles@example.com")
    project = client.post("/api/v1/projects", json={"name": "Profiles"}).json()
    design = client.post(
        "/api/v1/pcb/import",
        data={"project_id": project["id"]},
        files={"file": ("ref.kicad_pcb", REF, "application/octet-stream")},
    ).json()["design"]
    return project, design


def test_builtins_are_listed_first(client, setup):
    project, _ = setup
    profiles = client.get(f"/api/v1/projects/{project['id']}/manufacturing-profiles").json()
    assert [p["key"] for p in profiles] == ["via-conservative", "via-advanced"]
    assert all(p["builtin"] and "not any manufacturer" in p["source"] for p in profiles)


def test_crud_and_snapshot_into_runs(client, setup):
    project, design = setup
    url = f"/api/v1/projects/{project['id']}/manufacturing-profiles"
    created = client.post(url, json={"name": "Shop A", "values": VALUES})
    assert created.status_code == 201
    key = created.json()["key"]
    assert client.post(url, json={"name": "Shop A", "values": VALUES}).status_code == 409
    bad = client.post(url, json={"name": "Bad", "values": {**VALUES, "min_clearance": -1}})
    assert bad.status_code == 422

    run = client.post(f"/api/v1/designs/{design['id']}/analysis-runs",
                      json={"checks": ["mfg_track_width"], "options": {"profile": key}}).json()  # fmt: skip
    snapshot = run["config"]["options"]["manufacturing_profile"]
    assert snapshot["name"] == "Shop A" and snapshot["min_track_width"] == 0.3
    # Reference tracks are 0.25 and 0.3 mm wide: only the 0.25 mm ones are below Shop A's 0.3 mm.
    findings = client.get(f"/api/v1/analysis-runs/{run['id']}/findings").json()["items"]
    assert findings
    detail = client.get(f"/api/v1/findings/{findings[0]['id']}").json()
    assert any("Shop A" in e["label"] for e in detail["evidence"])

    # Editing the profile changes future runs only.
    client.patch(f"/api/v1/manufacturing-profiles/{key}", json={"values": {**VALUES, "min_track_width": 0.1}})
    again = client.get(f"/api/v1/analysis-runs/{run['id']}").json()
    assert again["config"]["options"]["manufacturing_profile"]["min_track_width"] == 0.3
    assert client.delete(f"/api/v1/manufacturing-profiles/{key}").status_code == 204
    assert [p["key"] for p in client.get(url).json()] == ["via-conservative", "via-advanced"]


def test_default_profile_and_unknown_profile(client, setup):
    _, design = setup
    run = client.post(f"/api/v1/designs/{design['id']}/analysis-runs", json={"checks": ["mfg_vias"]}).json()
    assert run["config"]["options"]["manufacturing_profile"]["key"] == "via-conservative"
    resp = client.post(f"/api/v1/designs/{design['id']}/analysis-runs", json={"options": {"profile": "fab-x"}})
    assert resp.status_code == 422 and resp.json()["error"]["code"] == "unknown_profile"


def test_profiles_of_other_projects_cant_be_used(client, make_client, setup):
    _, design = setup
    other = make_client()
    register(other, "other@example.com")
    theirs = other.post("/api/v1/projects", json={"name": "Theirs"}).json()
    key = other.post(
        f"/api/v1/projects/{theirs['id']}/manufacturing-profiles", json={"name": "T", "values": VALUES}
    ).json()["key"]
    resp = client.post(f"/api/v1/designs/{design['id']}/analysis-runs", json={"options": {"profile": key}})
    assert resp.status_code == 422


def test_power_and_impedance_options_reach_the_checks(client, setup):
    _, design = setup
    run = client.post(
        f"/api/v1/designs/{design['id']}/analysis-runs",
        json={"checks": ["track_current_capacity", "impedance_estimate"],
              "options": {"power": {"nets": {"VCC": 3.0}, "copper_thickness_mm": 0.035},
                          "impedance": {"nets": {"SIG": 50}}}},
    ).json()  # fmt: skip
    run = client.get(f"/api/v1/analysis-runs/{run['id']}").json()
    checks = {c["check_id"]: c for c in run["checks"]}
    assert checks["track_current_capacity"]["status"] == "ok"
    assert checks["impedance_estimate"]["status"] == "skipped"  # the reference board has no stackup
    findings = client.get(f"/api/v1/analysis-runs/{run['id']}/findings").json()["items"]
    assert [f["rule"] for f in findings] == ["track_too_narrow_for_current"]  # 0.25 mm tracks vs ~1.4 mm for 3 A
    bad = client.post(
        f"/api/v1/designs/{design['id']}/analysis-runs", json={"options": {"power": {"nets": {"VCC": -1}}}}
    )
    assert bad.status_code == 422
