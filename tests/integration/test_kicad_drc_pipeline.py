"""Worker-side KiCad DRC: sandboxed bundle → internal service → kicad_drc findings.

The service is faked here with a local HTTP server returning KiCad 9.0.6's real report for the
reference board; the real service (KiCad in Docker) runs in CI's end-to-end job.
"""

from __future__ import annotations

import io
import json
import threading
import zipfile
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

import pytest

from tests.integration.conftest import register

FIXTURES = Path(__file__).resolve().parents[1] / "engineering" / "fixtures"
REF = (FIXTURES / "via_reference_v8.kicad_pcb").read_bytes()
REPORT = json.loads((FIXTURES / "via_reference_v8.kicad_drc.json").read_text())


@pytest.fixture
def fake_eda(settings):
    received: list[dict[str, bytes]] = []
    behaviour = {"mode": "ok"}

    class Handler(BaseHTTPRequestHandler):
        def log_message(self, *args):  # quiet
            pass

        def do_POST(self):
            body = self.rfile.read(int(self.headers["Content-Length"]))
            with zipfile.ZipFile(io.BytesIO(body)) as zf:
                received.append({n: zf.read(n) for n in zf.namelist()})
            if behaviour["mode"] == "fail":
                payload = {
                    "ok": False,
                    "error": {"code": "drc_failed", "message": "KiCad couldn't load or check this board."},
                }
            elif behaviour["mode"] == "busy":
                self.send_response(503)
                self.end_headers()
                self.wfile.write(
                    b'{"ok": false, "error": {"code": "busy", "message": "KiCad DRC is busy; retry later."}}'
                )
                return
            else:
                rules = "project_file" if "board.kicad_pro" in received[-1] else "defaults"
                payload = {
                    "ok": True,
                    "report": REPORT,
                    "rules": rules,
                    "kicad_version": "9.0.6",
                    "duration_seconds": 1.0,
                }
            data = json.dumps(payload).encode()
            self.send_response(200)
            self.send_header("Content-Length", str(len(data)))
            self.end_headers()
            self.wfile.write(data)

    httpd = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    threading.Thread(target=httpd.serve_forever, daemon=True).start()
    settings.eda_url = f"http://127.0.0.1:{httpd.server_address[1]}"
    yield received, behaviour
    httpd.shutdown()
    httpd.server_close()


def zip_project() -> bytes:
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as zf:
        zf.writestr("proj/ref.kicad_pcb", REF)
        zf.writestr("proj/ref.kicad_pro", json.dumps({"board": {"design_settings": {"rules": {"min_clearance": 0.2}}}}))
        zf.writestr("proj/notes.txt", "not sent to KiCad")
    return buf.getvalue()


def analyse(client, filename, data):
    register(client, "drc@example.com")
    project = client.post("/api/v1/projects", json={"name": "DRC"}).json()
    imported = client.post(
        "/api/v1/pcb/import",
        data={"project_id": project["id"]},
        files={"file": (filename, data, "application/octet-stream")},
    ).json()
    run = client.post(f"/api/v1/designs/{imported['design']['id']}/analysis-runs", json={}).json()
    return client.get(f"/api/v1/analysis-runs/{run['id']}").json()


def test_project_archive_is_bundled_and_checked_with_its_rules(client, fake_eda):
    received, _ = fake_eda
    run = analyse(client, "ref.zip", zip_project())
    assert run["status"] == "succeeded"
    (bundle,) = received
    assert set(bundle) == {"board.kicad_pcb", "board.kicad_pro"}  # fixed names; other files dropped
    assert bundle["board.kicad_pcb"] == REF
    drc = next(c for c in run["checks"] if c["check_id"] == "kicad_drc")
    assert drc["status"] == "ok" and drc["finding_count"] == 15
    assert drc["details"]["rules"] == "project rules (.kicad_pro)" and drc["details"]["kicad_version"] == "9.0.6"
    findings = client.get(
        f"/api/v1/analysis-runs/{run['id']}/findings", params={"source": "kicad_drc", "limit": 50}
    ).json()
    assert findings["total"] == 15
    assert {f["verification"] for f in findings["items"]} == {"verified"}
    assert findings["facets"]["source"]["kicad_drc"] == 15


def test_bare_board_uses_default_rules(client, fake_eda):
    received, _ = fake_eda
    run = analyse(client, "ref.kicad_pcb", REF)
    assert set(received[0]) == {"board.kicad_pcb"}
    findings = client.get(
        f"/api/v1/analysis-runs/{run['id']}/findings", params={"source": "kicad_drc", "limit": 50}
    ).json()
    assert {f["verification"] for f in findings["items"]} == {"heuristic"}


@pytest.mark.parametrize(
    ("mode", "message"),
    [("fail", "KiCad couldn't load or check this board."), ("busy", "KiCad DRC is busy; retry later.")],
)
def test_service_errors_skip_the_check_with_the_reason(client, fake_eda, mode, message):
    _, behaviour = fake_eda
    behaviour["mode"] = mode
    run = analyse(client, "ref.kicad_pcb", REF)
    assert run["status"] == "succeeded"  # other checks still ran
    drc = next(c for c in run["checks"] if c["check_id"] == "kicad_drc")
    assert drc["status"] == "skipped" and message in drc["message"]


def test_unreachable_service_skips_the_check(client, settings):
    settings.eda_url = "http://127.0.0.1:9"  # nothing listens there
    run = analyse(client, "ref.kicad_pcb", REF)
    drc = next(c for c in run["checks"] if c["check_id"] == "kicad_drc")
    assert drc["status"] == "skipped" and "couldn't be reached" in drc["message"]


def test_not_configured(client):
    run = analyse(client, "ref.kicad_pcb", REF)
    drc = next(c for c in run["checks"] if c["check_id"] == "kicad_drc")
    assert drc["status"] == "skipped" and "wasn't run" in drc["message"]
