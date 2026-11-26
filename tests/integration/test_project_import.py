"""Uploading KiCad project archives (.zip) through the API and the real sandboxed parser."""

from __future__ import annotations

import io
import json
import zipfile
from pathlib import Path

import pytest
from sqlalchemy import select

from tests.integration.conftest import register
from via_api.models import UploadRecord

REF = (Path(__file__).resolve().parents[1] / "engineering" / "fixtures" / "via_reference_v8.kicad_pcb").read_bytes()
PRO = {
    "board": {"design_settings": {"rules": {"min_clearance": 0.15, "min_track_width": 0.18}}},
    "net_settings": {
        "classes": [{"name": "Default", "clearance": 0.2}, {"name": "Power", "clearance": 0.3, "track_width": 0.5}],
        "netclass_patterns": [{"netclass": "Power", "pattern": "VCC"}],
    },
}


def make_zip(files: dict[str, bytes | str]) -> bytes:
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as zf:
        for name, data in files.items():
            zf.writestr(name, data)
    return buf.getvalue()


def upload(client, project_id, data, filename="ref.zip"):
    return client.post(
        "/api/v1/pcb/import",
        data={"project_id": project_id},
        files={"file": (filename, data, "application/zip")},
    )


@pytest.fixture
def project(client):
    register(client, "projects@example.com")
    return client.post("/api/v1/projects", json={"name": "Archives"}).json()


def test_project_archive_is_parsed_with_its_design_rules(client, project):
    data = make_zip({"ref/ref.kicad_pcb": REF, "ref/ref.kicad_pro": json.dumps(PRO)})
    resp = upload(client, project["id"], data)
    assert resp.status_code == 202, resp.text
    body = resp.json()
    assert body["design"]["name"] == "ref"
    rev = client.get(f"/api/v1/revisions/{body['revision']['id']}").json()
    assert rev["status"] == "ready", rev
    assert rev["source_format"] == "kicad"
    assert rev["object_counts"]["component_count"] == 4

    summary = client.get(f"/api/v1/pcb/{body['design']['id']}").json()
    constraints = summary["constraints"]
    assert constraints["rules_source"] == "project_file"
    assert constraints["rules"]["min_clearance"] == 0.15
    power = next(nc for nc in constraints["net_classes"] if nc["name"] == "Power")
    assert power["nets"] == ["VCC"] and power["track_width"] == 0.5
    assert summary["source"]["board_file"] == "ref/ref.kicad_pcb"
    assert summary["source"]["project_files"] == ["ref/ref.kicad_pro"]

    # The stored source is the archive exactly as uploaded.
    (source,) = [f for f in client.get(f"/api/v1/files?project_id={project['id']}").json() if f["kind"] == "source"]
    assert source["original_filename"] == "ref.zip"
    assert client.get(f"/api/v1/files/{source['id']}/download").content == data


def test_bare_board_upload_is_labelled_board_rules_only(client, project):
    resp = client.post(
        "/api/v1/pcb/import",
        data={"project_id": project["id"]},
        files={"file": ("ref.kicad_pcb", REF, "application/octet-stream")},
    )
    summary = client.get(f"/api/v1/pcb/{resp.json()['design']['id']}").json()
    assert summary["constraints"]["rules_source"] == "board_file"
    assert summary["constraints"]["rules"] is None


@pytest.mark.parametrize(
    ("files", "message"),
    [
        ({"readme.txt": "no board here"}, "doesn't contain a .kicad_pcb"),
        ({"../escape.kicad_pcb": REF}, "unsafe path"),
        ({"a.kicad_pcb": REF, "b.kicad_pcb": REF}, "several boards"),
    ],
    ids=["no-board", "unsafe-path", "ambiguous"],
)
def test_unusable_archives_are_rejected_at_upload_and_recorded(client, project, db, files, message):
    resp = upload(client, project["id"], make_zip(files))
    assert resp.status_code == 422
    err = resp.json()["error"]
    assert err["code"] == "invalid_project_archive" and message in err["message"]
    record = db.scalar(select(UploadRecord).order_by(UploadRecord.created_at.desc()))
    assert (record.outcome.value, record.rejection_reason) == ("rejected", "invalid_archive")
    assert client.get(f"/api/v1/designs?project_id={project['id']}").json() == []


def test_board_inside_archive_obeys_the_upload_limit(client, project, settings):
    settings.max_upload_bytes = 4096  # the zip is ~2 KB, the board inside ~8 KB
    data = make_zip({"ref.kicad_pcb": REF})
    assert len(data) < 4096 < len(REF)
    resp = upload(client, project["id"], data)
    assert resp.status_code == 422
    assert "larger than" in resp.json()["error"]["message"]


def test_archive_with_a_broken_board_fails_parsing_visibly(client, project):
    resp = upload(client, project["id"], make_zip({"bad.kicad_pcb": "(kicad_pcb (version 20240108"}))
    assert resp.status_code == 202
    rev = client.get(f"/api/v1/revisions/{resp.json()['revision']['id']}").json()
    assert rev["status"] == "failed" and rev["error_code"] == "invalid_file"


def test_duplicate_archives_are_detected(client, project):
    data = make_zip({"ref.kicad_pcb": REF, "ref.kicad_pro": json.dumps(PRO)})
    assert upload(client, project["id"], data).status_code == 202
    assert upload(client, project["id"], data, filename="again.zip").json()["error"]["code"] == "duplicate_file"


def test_limits_list_project_archives(client, project):
    formats = client.get("/api/v1/pcb/limits").json()["formats"]
    assert {"id": "kicad_project", "name": "KiCad project (.zip)", "extensions": [".zip"]} in formats


def test_wrong_extension_with_zip_content_is_not_treated_as_an_archive(client, project):
    resp = upload(client, project["id"], make_zip({"ref.kicad_pcb": REF}), filename="sneaky.kicad_pcb")
    assert resp.status_code == 415  # zip bytes under a board name: neither a board nor an archive
