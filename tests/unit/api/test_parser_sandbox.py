"""The parser sandbox: correct results, failure handling and isolation."""

from __future__ import annotations

import dataclasses
import json
import os
import sys
from pathlib import Path

import pytest

from via_api.parsing.sandbox import (
    PARSER_CRASHED,
    PARSER_INVALID_OUTPUT,
    PARSER_RESOURCE_LIMIT,
    PARSER_TIMEOUT,
    SandboxLimits,
    parser_command,
    run_parser,
)

FIXTURE = Path(__file__).resolve().parents[2] / "engineering" / "fixtures" / "via_reference_v8.kicad_pcb"
LIMITS = SandboxLimits(timeout_seconds=20, memory_bytes=1024**3)


def py(code: str) -> list[str]:
    return [sys.executable, "-I", "-B", "-c", code]


def test_parses_a_real_board_in_a_subprocess():
    outcome = run_parser(FIXTURE.read_bytes(), "via_reference_v8.kicad_pcb", LIMITS)
    assert outcome.ok, outcome
    assert outcome.design.stats.component_count == 4
    assert outcome.design.source.filename == "via_reference_v8.kicad_pcb"


def test_invalid_files_return_the_engine_error():
    outcome = run_parser(b"(kicad_pcb (version 1) (net 1", "broken.kicad_pcb", LIMITS)
    assert (outcome.error_code, outcome.ok) == ("invalid_file", False)
    assert "Malformed" in outcome.error_message


def test_unrecognized_files_are_reported():
    outcome = run_parser(b"\xd0\xcf\x11\xe0", "board.PcbDoc", LIMITS)
    assert outcome.error_code == "unsupported_format"


def test_corrupt_project_archives_are_reported():
    outcome = run_parser(b"PK\x03\x04 truncated", "project.zip", LIMITS)
    assert outcome.error_code == "invalid_archive"
    assert "zip" in outcome.error_message


def test_archive_board_size_limit_is_passed_to_the_parser():
    import io
    import zipfile

    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_STORED) as zf:
        zf.writestr("big.kicad_pcb", b"(kicad_pcb (version 20240108))" + b" " * 4096)
    outcome = run_parser(buf.getvalue(), "p.zip", dataclasses.replace(LIMITS, max_archive_board_bytes=1024))
    assert outcome.error_code == "invalid_archive"
    assert "larger than" in outcome.error_message


def test_filename_is_reduced_to_a_safe_basename():
    assert parser_command("../../etc/passwd")[-1] == "passwd"
    assert parser_command("C:\\Users\\x\\board $(rm -rf ~);.kicad_pcb")[-1] == "board __rm -rf ___.kicad_pcb"
    cmd = parser_command("board.kicad_pcb")
    assert cmd[:5] == [sys.executable, "-I", "-B", "-m", "via_pcb.cli"]


def test_timeouts_are_enforced():
    outcome = run_parser(b"", None, SandboxLimits(timeout_seconds=1), command=py("while True: pass"))
    assert outcome.error_code in (PARSER_TIMEOUT, PARSER_RESOURCE_LIMIT)
    assert outcome.duration_seconds < 5


def test_memory_limit_is_enforced():
    limits = SandboxLimits(timeout_seconds=10, memory_bytes=256 * 1024**2)
    outcome = run_parser(b"", None, limits, command=py("x = bytearray(1024**3)"))
    assert outcome.error_code == PARSER_RESOURCE_LIMIT


def test_child_gets_no_credentials_from_the_environment(monkeypatch):
    monkeypatch.setenv("VIA_SECRET_KEY", "super-secret")
    monkeypatch.setenv("VIA_S3_SECRET_KEY", "storage-secret")
    code = (
        "import os, json, sys; "
        "names = json.dumps(sorted(os.environ)); "
        "sys.stdout.write(json.dumps({'ok': False, 'error': {'code': 'env', 'message': names}}))"
    )
    outcome = run_parser(b"", None, LIMITS, command=py(code))
    env_names = json.loads(outcome.error_message)
    assert not any(name.startswith("VIA_") for name in env_names)
    assert set(env_names) <= {"PATH", "LANG", "PYTHONHASHSEED", "LC_CTYPE"}


def test_child_cannot_write_file_contents():
    # RLIMIT_FSIZE=0: writes fail with EFBIG (Python ignores SIGXFSZ, so it surfaces as OSError).
    code = (
        "import json, sys\n"
        "try:\n"
        "    f = open('out.txt', 'w'); f.write('x' * 100); f.flush(); result = 'written'\n"
        "except OSError as e:\n"
        "    result = f'blocked:{e.errno}'\n"
        "sys.stdout.write(json.dumps({'ok': False, 'error': {'code': 'probe', 'message': result}}))"
    )
    outcome = run_parser(b"", None, LIMITS, command=py(code))
    assert outcome.error_message == "blocked:27"  # EFBIG


@pytest.mark.skipif(os.geteuid() == 0, reason="RLIMIT_NPROC is not enforced for root")
def test_child_cannot_start_processes():
    outcome = run_parser(b"", None, LIMITS, command=py("import os; os.fork()"))
    assert outcome.error_code == PARSER_CRASHED


def test_garbage_output_is_rejected():
    outcome = run_parser(b"", None, LIMITS, command=py("print('not json')"))
    assert outcome.error_code == PARSER_INVALID_OUTPUT
    schema_violation = py("import json; print(json.dumps({'ok': True, 'design': {'nope': 1}}))")
    assert run_parser(b"", None, LIMITS, command=schema_violation).error_code == PARSER_INVALID_OUTPUT


def test_crash_details_are_not_exposed():
    outcome = run_parser(b"", None, LIMITS, command=py("raise RuntimeError('/secret/path leaked')"))
    assert outcome.error_code == PARSER_CRASHED
    assert "secret" not in outcome.error_message


def test_bundler_repacks_boards_and_projects_with_fixed_names():
    import io
    import zipfile

    from via_api.parsing.sandbox import run_bundler

    board = b"(kicad_pcb (version 20240108))"
    out = run_bundler(board, "x.kicad_pcb", LIMITS)
    assert out.bundle is not None
    assert zipfile.ZipFile(io.BytesIO(out.bundle)).namelist() == ["board.kicad_pcb"]
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as zf:
        zf.writestr("p/p.kicad_pcb", board)
        zf.writestr("p/p.kicad_pro", "{}")
        zf.writestr("p/p.kicad_dru", "(version 1)")
        zf.writestr("p/README.md", "dropped")
    out = run_bundler(buf.getvalue(), "p.zip", LIMITS)
    names = sorted(zipfile.ZipFile(io.BytesIO(out.bundle)).namelist())
    assert names == ["board.kicad_dru", "board.kicad_pcb", "board.kicad_pro"]
    bad = run_bundler(b"PK\x03\x04 broken", "p.zip", LIMITS)
    assert bad.bundle is None and bad.error_code == "invalid_archive"
    not_kicad = run_bundler(b"hello", "x.kicad_pcb", LIMITS)
    assert not_kicad.bundle is None and not_kicad.error_code == "invalid_archive"
