"""The KiCad tool service, with a fake kicad-cli (the real one runs in CI's end-to-end job)."""

from __future__ import annotations

import io
import json
import os
import stat
import sys
import threading
import urllib.error
import urllib.request
import zipfile
from http.server import ThreadingHTTPServer
from pathlib import Path

import pytest
from via_eda.drc import BundleError, Limits, read_bundle, run_drc
from via_eda.server import Config, make_handler

FAKE_CLI = """#!{python}
import json, os, sys, time
args = sys.argv[1:]
if args == ["version"]:
    print("9.0.6"); sys.exit(0)
out = args[args.index("--output") + 1]
board = open(args[-1]).read()
project = os.path.exists(args[-1][: -len("kicad_pcb")] + "kicad_pro")
seen = {{"args": args, "env": sorted(os.environ), "project": project}}
if "FAIL" in board:
    sys.exit(3)
if "SLEEP" in board:
    time.sleep(30)
json.dump({{"violations": [], "unconnected_items": [], "seen": seen}}, open(out, "w"))
"""


@pytest.fixture
def fake_cli(tmp_path: Path) -> str:
    path = tmp_path / "kicad-cli"
    path.write_text(FAKE_CLI.format(python=sys.executable))
    path.chmod(path.stat().st_mode | stat.S_IEXEC)
    return str(path)


def bundle(**members: bytes) -> bytes:
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as zf:
        for name, data in members.items():
            zf.writestr(name, data)
    return buf.getvalue()


BOARD = b"(kicad_pcb (version 20240108))"


def test_bundle_accepts_only_fixed_names():
    files = read_bundle(bundle(**{"board.kicad_pcb": BOARD, "board.kicad_pro": b"{}"}), Limits())
    assert set(files) == {"board.kicad_pcb", "board.kicad_pro"}
    for bad in ({"../board.kicad_pcb": BOARD}, {"board.kicad_pcb": BOARD, "evil.sh": b"x"}, {"board.kicad_pro": b"{}"}):
        with pytest.raises(BundleError):
            read_bundle(bundle(**bad), Limits())
    with pytest.raises(BundleError, match="valid zip"):
        read_bundle(b"not a zip", Limits())
    with pytest.raises(BundleError, match="too large"):
        read_bundle(bundle(**{"board.kicad_pcb": BOARD}), Limits(max_member_bytes=4))


def test_drc_runs_with_minimal_environment_and_limits(fake_cli):
    files = {"board.kicad_pcb": BOARD, "board.kicad_pro": b"{}"}
    result = run_drc(files, Limits(timeout_seconds=20), kicad_cli=fake_cli)
    assert result.ok and result.rules == "project_file"
    seen = result.report["seen"]
    assert seen["project"] is True
    assert "--severity-error" in seen["args"] and "--severity-all" not in seen["args"]  # exclusions stay excluded
    leaked = {k for k in seen["env"] if k.startswith(("VIA_", "AWS", "POSTGRES", "MINIO"))}
    assert leaked == set() and "HOME" in seen["env"]


def test_defaults_without_project_file(fake_cli):
    assert run_drc({"board.kicad_pcb": BOARD}, Limits(), kicad_cli=fake_cli).rules == "defaults"


def test_failures_and_timeouts_are_reported_safely(fake_cli):
    failed = run_drc({"board.kicad_pcb": b"FAIL"}, Limits(), kicad_cli=fake_cli)
    assert (failed.ok, failed.error_code) == (False, "drc_failed")
    assert "couldn't load" in failed.error_message
    slow = run_drc({"board.kicad_pcb": b"SLEEP"}, Limits(timeout_seconds=1), kicad_cli=fake_cli)
    assert (slow.ok, slow.error_code) == (False, "timeout")


def test_temp_files_are_removed(fake_cli, tmp_path, monkeypatch):
    monkeypatch.setenv("TMPDIR", str(tmp_path / "t"))
    os.makedirs(tmp_path / "t")
    import tempfile

    monkeypatch.setattr(tempfile, "tempdir", None)
    run_drc({"board.kicad_pcb": BOARD}, Limits(), kicad_cli=fake_cli)
    assert os.listdir(tmp_path / "t") == []


@pytest.fixture
def server(fake_cli):
    config = Config({"VIA_EDA_PORT": "0", "VIA_EDA_KICAD_CLI": fake_cli, "VIA_EDA_MAX_BODY_BYTES": "4096",
                     "VIA_EDA_CONCURRENCY": "1"})  # fmt: skip
    httpd = ThreadingHTTPServer(("127.0.0.1", 0), make_handler(config))
    thread = threading.Thread(target=httpd.serve_forever, daemon=True)
    thread.start()
    yield f"http://127.0.0.1:{httpd.server_address[1]}"
    httpd.shutdown()
    httpd.server_close()


def post(url: str, data: bytes) -> tuple[int, dict]:
    req = urllib.request.Request(f"{url}/drc", data=data, method="POST")
    try:
        with urllib.request.urlopen(req, timeout=30) as resp:
            return resp.status, json.loads(resp.read())
    except urllib.error.HTTPError as exc:
        with exc:
            return exc.code, json.loads(exc.read())


def test_server_health_and_drc(server):
    with urllib.request.urlopen(f"{server}/health", timeout=30) as resp:
        assert json.loads(resp.read()) == {"status": "ok", "kicad_version": "9.0.6"}
    status, body = post(server, bundle(**{"board.kicad_pcb": BOARD}))
    assert status == 200 and body["ok"] and body["rules"] == "defaults" and body["kicad_version"] == "9.0.6"


def test_server_rejects_bad_input(server):
    status, body = post(server, b"nope")
    assert status == 400 and body["error"]["code"] == "invalid_bundle"
    status, body = post(server, b"x" * 5000)
    assert status == 413
    with pytest.raises(urllib.error.HTTPError) as exc:
        urllib.request.urlopen(f"{server}/anything", timeout=10)
    assert exc.value.code == 404
    exc.value.close()
