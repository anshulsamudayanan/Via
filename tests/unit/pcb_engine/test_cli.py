import io
import json
import sys
from pathlib import Path

from via_pcb import cli

FIXTURE = Path(__file__).resolve().parents[2] / "engineering" / "fixtures" / "via_legacy_v5.kicad_pcb"


def run(monkeypatch, capsys, data: bytes, *args: str) -> dict:
    monkeypatch.setattr(sys, "stdin", io.TextIOWrapper(io.BytesIO(data)))
    assert cli.main(list(args)) == 0
    return json.loads(capsys.readouterr().out)


def test_cli_outputs_the_full_design(monkeypatch, capsys):
    out = run(monkeypatch, capsys, FIXTURE.read_bytes(), "--filename", "via_legacy_v5.kicad_pcb")
    assert out["ok"] is True
    assert out["design"]["stats"]["component_count"] == 1
    assert out["design"]["components"][0]["reference"] == "R1"


def test_cli_summary_and_errors(monkeypatch, capsys):
    summary = run(monkeypatch, capsys, FIXTURE.read_bytes(), "--filename", "x.kicad_pcb", "--summary")
    assert set(summary["design"]) == {"source", "title", "stats", "warnings"}
    bad = run(monkeypatch, capsys, b"hello", "--filename", "x.kicad_pcb")
    assert bad == {"ok": False, "error": {"code": "unsupported_format", "message": bad["error"]["message"]}}
