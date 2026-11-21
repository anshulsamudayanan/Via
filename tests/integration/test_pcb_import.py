"""PCB upload, background parsing (inline, real sandbox), and the design/PCB/file endpoints."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path

import pytest
from sqlalchemy import select

from tests.integration.conftest import register
from via_api.models import ActivityLog, DesignFile, PCBComponent, UploadRecord
from via_pcb import PCBDesign

FIXTURES = Path(__file__).resolve().parents[1] / "engineering" / "fixtures"
REF = (FIXTURES / "via_reference_v8.kicad_pcb").read_bytes()
LEGACY = (FIXTURES / "via_legacy_v5.kicad_pcb").read_bytes()


def upload(client, project_id, data=REF, filename="via_reference_v8.kicad_pcb", **form):
    return client.post(
        "/api/v1/pcb/import",
        data={"project_id": project_id, **form},
        files={"file": (filename, data, "application/octet-stream")},
    )


@pytest.fixture
def project(client):
    register(client, "eng@example.com", "Eng")
    return client.post("/api/v1/projects", json={"name": "Board"}).json()


def stored_files(settings) -> list[Path]:
    root = settings.local_storage_path
    return [p for p in root.rglob("*") if p.is_file() and not p.name.endswith(".meta")] if root.exists() else []


def test_upload_parses_and_exposes_board_data(client, project, db, settings):
    resp = upload(client, project["id"])
    assert resp.status_code == 202, resp.json()
    body = resp.json()
    design, revision = body["design"], body["revision"]
    assert design["name"] == "via_reference_v8"
    assert revision["revision_number"] == 1
    assert revision["source_format"] == "kicad"
    assert revision["source_sha256"] == hashlib.sha256(REF).hexdigest()
    assert revision["source_file"]["size_bytes"] == len(REF)
    assert revision["source_file"]["original_filename"] == "via_reference_v8.kicad_pcb"

    rev = client.get(f"/api/v1/revisions/{revision['id']}").json()
    assert rev["status"] == "ready"
    assert rev["parser_version"] == "0.1.0" and rev["schema_version"] == "1.0.0"
    assert rev["imported_at"] is not None
    assert rev["warnings"] == []
    assert rev["object_counts"]["component_count"] == 4

    summary = client.get(f"/api/v1/pcb/{design['id']}").json()
    assert summary["title"] == "VIA Reference Board"
    assert summary["source"]["filename"] == "via_reference_v8.kicad_pcb"
    assert summary["source"]["format_version"] == "20240108"
    assert summary["constraints"]["pad_to_mask_clearance"] == 0.05
    assert summary["geometry"]["width"] == 50 and summary["geometry"]["height"] == 30
    assert summary["geometry"]["outline_closed"] is True and summary["geometry"]["copper_layer_count"] == 2
    assert summary["stats"]["via_count"] == 1

    # File contents live in object storage, not PostgreSQL.
    files = stored_files(settings)
    assert len(files) == 2  # source + normalized.json.gz
    assert any(f.read_bytes() == REF for f in files)
    assert all(len(f.storage_key) < 200 for f in db.scalars(select(DesignFile)))


def test_components_nets_and_layers(client, project):
    design_id = upload(client, project["id"]).json()["design"]["id"]
    comps = client.get(f"/api/v1/pcb/{design_id}/components").json()
    assert comps["total"] == 4
    assert [c["reference"] for c in comps["items"]] == ["C1", "H1", "J1", "R1"]
    r1 = comps["items"][3]
    assert (r1["value"], r1["footprint"], r1["x"], r1["y"], r1["side"], r1["pad_count"]) == (
        "10k",
        "Resistor_SMD:R_0603_1608Metric",
        110,
        110,
        "top",
        2,
    )
    assert client.get(f"/api/v1/pcb/{design_id}/components?q=10K").json()["items"][0]["reference"] == "R1"
    assert [c["reference"] for c in client.get(f"/api/v1/pcb/{design_id}/components?side=bottom").json()["items"]] == [
        "C1"
    ]
    page = client.get(f"/api/v1/pcb/{design_id}/components?limit=2&offset=2").json()
    assert [c["reference"] for c in page["items"]] == ["J1", "R1"]
    assert client.get(f"/api/v1/pcb/{design_id}/components?side=left").status_code == 422

    nets = client.get(f"/api/v1/pcb/{design_id}/nets").json()
    assert [(n["name"], n["pad_count"], n["via_count"]) for n in nets["items"]] == [
        ("GND", 2, 0),
        ("SIG", 2, 1),
        ("VCC", 2, 0),
    ]
    assert client.get(f"/api/v1/pcb/{design_id}/nets?q=vc").json()["total"] == 1

    layers = client.get(f"/api/v1/pcb/{design_id}/layers").json()
    assert len(layers) == 18
    assert layers[0] == {
        "ordinal": 0,
        "name": "F.Cu",
        "kind": "copper",
        "side": "top",
        "source_type": "signal",
        "user_name": None,
    }


def test_natural_sort_of_references(client, project, db):
    design_id = upload(client, project["id"]).json()["design"]["id"]
    # Re-label stored components to check ordering independent of fixture content.
    for comp, ref in zip(db.scalars(select(PCBComponent)).all(), ["R10", "R2", "R1", "C3"], strict=True):
        comp.reference = ref
    db.flush()
    refs = [c["reference"] for c in client.get(f"/api/v1/pcb/{design_id}/components").json()["items"]]
    assert refs == ["C3", "R1", "R2", "R10"]


def test_normalized_design_download(client, project):
    design_id = upload(client, project["id"]).json()["design"]["id"]
    resp = client.get(f"/api/v1/pcb/{design_id}/normalized")
    assert resp.status_code == 200
    assert resp.headers["content-encoding"] == "gzip"
    design = PCBDesign.model_validate_json(resp.content)
    assert design.stats.track_count == 8 and len(design.vias) == 1


def test_files_list_and_download(client, project):
    upload(client, project["id"])
    files = client.get(f"/api/v1/files?project_id={project['id']}").json()
    assert len(files) == 1  # normalized JSON is internal, not listed as a user file
    f = files[0]
    assert (f["design_name"], f["revision_number"], f["sha256"]) == (
        "via_reference_v8",
        1,
        hashlib.sha256(REF).hexdigest(),
    )
    dl = client.get(f"/api/v1/files/{f['id']}/download")
    assert dl.status_code == 200 and dl.content == REF
    assert dl.headers["content-type"] == "application/octet-stream"
    assert dl.headers["content-disposition"].startswith('attachment; filename="via_reference_v8.kicad_pcb"')


def test_duplicate_uploads_are_detected_by_hash(client, project, db):
    first = upload(client, project["id"]).json()
    dup = upload(client, project["id"], filename="renamed.kicad_pcb")
    assert dup.status_code == 409
    err = dup.json()["error"]
    assert err["code"] == "duplicate_file"
    assert err["details"]["design_id"] == first["design"]["id"]
    assert "revision 1" in err["message"]
    outcomes = [r.outcome for r in db.scalars(select(UploadRecord).order_by(UploadRecord.created_at))]
    assert outcomes == ["accepted", "duplicate"]


def test_new_revision_of_an_existing_design(client, project):
    design_id = upload(client, project["id"]).json()["design"]["id"]
    resp = upload(client, project["id"], data=LEGACY, filename="v2.kicad_pcb", design_id=design_id)
    assert resp.status_code == 202 and resp.json()["revision"]["revision_number"] == 2
    detail = client.get(f"/api/v1/designs/{design_id}").json()
    assert detail["revision_count"] == 2
    assert detail["current_revision"]["revision_number"] == 2
    assert [r["revision_number"] for r in detail["revisions"]] == [2, 1]
    assert client.get(f"/api/v1/pcb/{design_id}").json()["stats"]["component_count"] == 1
    old = detail["revisions"][1]["id"]
    assert client.get(f"/api/v1/pcb/{design_id}?revision_id={old}").json()["stats"]["component_count"] == 4


@pytest.mark.parametrize(
    "data, filename, status, code",
    [
        (REF, "board.txt", 415, "unsupported_file_type"),
        (b"PK\x03\x04zipfile", "board.kicad_pcb", 415, "unsupported_file_type"),
        (b"(kicad_sch (version 20231120))", "board.kicad_pcb", 415, "unsupported_file_type"),
        (b"", "board.kicad_pcb", 422, "empty_file"),
    ],
)
def test_invalid_uploads_are_rejected_and_recorded(client, project, db, settings, data, filename, status, code):
    resp = upload(client, project["id"], data=data, filename=filename)
    assert resp.status_code == status
    assert resp.json()["error"]["code"] == code
    assert db.scalar(select(UploadRecord)).outcome == "rejected"
    assert stored_files(settings) == []  # nothing stored
    assert client.get(f"/api/v1/designs?project_id={project['id']}").json() == []


def test_parse_failures_are_reported_and_retryable(client, project, db):
    broken = b'(kicad_pcb (version 20240108) (net 1 "GND"'
    resp = upload(client, project["id"], data=broken, filename="broken.kicad_pcb")
    assert resp.status_code == 202
    rev = resp.json()["revision"]
    assert rev["status"] == "failed"
    assert rev["error_code"] == "invalid_file"
    assert "Malformed" in rev["error_message"]
    design_id = resp.json()["design"]["id"]
    not_parsed = client.get(f"/api/v1/pcb/{design_id}")
    assert not_parsed.status_code == 409 and not_parsed.json()["error"]["code"] == "not_parsed"
    # A failed file is not a "duplicate": the user may retry it.
    assert upload(client, project["id"], data=broken, filename="broken.kicad_pcb").status_code == 202
    assert db.scalar(select(ActivityLog).where(ActivityLog.action == "design.parse_failed")) is not None


def test_upload_size_limit(client, project, settings):
    settings.max_upload_bytes = 1000
    resp = upload(client, project["id"], data=b"(kicad_pcb " + b" " * 5000 + b")")
    assert resp.status_code == 413 and resp.json()["error"]["code"] == "payload_too_large"


def test_upload_requires_content_length(client, project):
    def body():
        yield b"--x\r\n"

    resp = client.post(
        "/api/v1/pcb/import", content=body(), headers={"Content-Type": "multipart/form-data; boundary=x"}
    )
    assert resp.status_code == 411


def test_queue_failure_marks_the_revision_failed(client, project, job_queue):
    job_queue.fail = True
    resp = upload(client, project["id"])
    assert resp.status_code == 503 and resp.json()["error"]["code"] == "queue_unavailable"
    design = client.get(f"/api/v1/designs?project_id={project['id']}").json()[0]
    assert design["latest_revision"]["status"] == "failed"
    assert design["latest_revision"]["error_code"] == "queue_unavailable"


def test_pending_revisions_until_the_worker_runs(client, project, job_queue):
    job_queue.run = False
    rev = upload(client, project["id"]).json()["revision"]
    assert rev["status"] == "pending"
    assert client.get(f"/api/v1/revisions/{rev['id']}").json()["status"] == "pending"


def test_rename_and_delete_design_removes_stored_files(client, project, settings, db):
    design_id = upload(client, project["id"]).json()["design"]["id"]
    renamed = client.patch(f"/api/v1/designs/{design_id}", json={"name": "Main board"})
    assert renamed.status_code == 200 and renamed.json()["name"] == "Main board"
    assert len(stored_files(settings)) == 2
    assert client.delete(f"/api/v1/designs/{design_id}").status_code == 204
    assert stored_files(settings) == []
    assert client.get(f"/api/v1/designs/{design_id}").status_code == 404
    assert db.scalar(select(PCBComponent)) is None


def test_deleting_a_project_removes_its_stored_files(client, project, settings):
    upload(client, project["id"])
    assert stored_files(settings)
    assert client.delete(f"/api/v1/projects/{project['id']}").status_code == 204
    assert stored_files(settings) == []


def test_project_design_count_and_activity(client, project):
    upload(client, project["id"])
    assert client.get(f"/api/v1/projects/{project['id']}").json()["design_count"] == 1
    actions = [a["action"] for a in client.get(f"/api/v1/activity?project_id={project['id']}").json()["items"]]
    assert actions[:2] == ["design.parsed", "design.uploaded"]


def test_upload_limits_endpoint(client, project, settings):
    limits = client.get("/api/v1/pcb/limits").json()
    assert limits["max_upload_bytes"] == settings.max_upload_bytes
    assert limits["formats"] == [{"id": "kicad", "name": "KiCad PCB", "extensions": [".kicad_pcb"]}]


def test_integrity_check_rejects_tampered_storage(client, project, settings, job_queue):
    job_queue.run = False
    rev = upload(client, project["id"]).json()["revision"]
    src = next(p for p in stored_files(settings) if p.name == "source")
    src.write_bytes(REF + b"tampered")
    job_queue.run = True
    job_queue.enqueue_import(__import__("uuid").UUID(rev["id"]))
    after = client.get(f"/api/v1/revisions/{rev['id']}").json()
    assert after["status"] == "failed" and after["error_code"] == "integrity_error"


def test_reprocessing_is_idempotent(client, project, job_queue, db):
    rev = upload(client, project["id"]).json()["revision"]
    job_queue.enqueue_import(__import__("uuid").UUID(rev["id"]))  # run the job a second time
    assert len(db.scalars(select(PCBComponent)).all()) == 4
    assert json.loads(json.dumps(client.get(f"/api/v1/revisions/{rev['id']}").json()))["status"] == "ready"


def test_oversized_requests_are_refused_before_reading_the_body(settings, db):
    from fastapi.testclient import TestClient

    from via_api.main import create_app

    small = settings.model_copy(update={"max_upload_bytes": 1000})
    with TestClient(create_app(small), headers={"X-VIA-Request": "1"}) as c:
        resp = c.post(
            "/api/v1/pcb/import",
            data={"project_id": "00000000-0000-0000-0000-000000000000"},
            files={"file": ("big.kicad_pcb", b"x" * (2 * 1024 * 1024), "application/octet-stream")},
        )
    # Rejected by the middleware: no auth lookup, no body parsing, no upload record.
    assert resp.status_code == 413
    assert db.scalar(select(UploadRecord)) is None
