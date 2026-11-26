"""Run the PCB parser in a constrained subprocess.

The parser processes untrusted files. It never executes them, but a malformed
or hostile file could still try to exhaust memory or CPU, or hit a parser bug.
So parsing never happens in the API or worker process itself:

* separate process: ``python -I -B -m via_pcb.cli`` (isolated mode: ignores
  ``PYTHON*`` env vars, the user site and the current directory),
* **empty environment**: no database URL, storage keys or secret key,
* rlimits: CPU seconds, address space, no file writes (``RLIMIT_FSIZE=0``),
  no new processes (``RLIMIT_NPROC=0``; not enforced for root), few file
  descriptors, no core dumps,
* wall-clock timeout, its own session/process group, empty temp working dir,
* input on stdin, result as JSON on stdout, validated against the
  normalized model before anything is stored.

Stronger isolation (separate container without network, gVisor) is documented
as future hardening in docs/SECURITY.md.
"""

from __future__ import annotations

import json
import logging
import os
import re
import resource
import signal
import subprocess
import sys
import tempfile
import time
from collections.abc import Callable, Sequence
from dataclasses import dataclass

from pydantic import ValidationError

from via_pcb import PCBDesign

logger = logging.getLogger("via_api.parsing")

#: Codes are stored on the revision and shown to users with the message.
PARSER_TIMEOUT = "parser_timeout"
PARSER_RESOURCE_LIMIT = "parser_resource_limit"
PARSER_CRASHED = "parser_crashed"
PARSER_INVALID_OUTPUT = "parser_invalid_output"


@dataclass(frozen=True)
class SandboxLimits:
    timeout_seconds: int = 60
    memory_bytes: int = 1024 * 1024 * 1024
    max_open_files: int = 64
    #: Largest board accepted inside a project archive (uncompressed); None = engine default.
    max_archive_board_bytes: int | None = None


@dataclass(frozen=True)
class ParseOutcome:
    design: PCBDesign | None
    error_code: str | None = None
    #: Safe to show to the user (never contains stderr or internal paths).
    error_message: str | None = None
    duration_seconds: float = 0.0

    @property
    def ok(self) -> bool:
        return self.design is not None


def _apply_limits(limits: SandboxLimits) -> Callable[[], None]:
    def apply() -> None:  # runs in the child between fork and exec
        cpu = limits.timeout_seconds
        resource.setrlimit(resource.RLIMIT_CPU, (cpu, cpu + 1))
        resource.setrlimit(resource.RLIMIT_AS, (limits.memory_bytes, limits.memory_bytes))
        resource.setrlimit(resource.RLIMIT_FSIZE, (0, 0))
        resource.setrlimit(resource.RLIMIT_NOFILE, (limits.max_open_files, limits.max_open_files))
        resource.setrlimit(resource.RLIMIT_CORE, (0, 0))
        resource.setrlimit(resource.RLIMIT_NPROC, (0, 0))

    return apply


def _safe_filename(filename: str | None) -> str | None:
    if not filename:
        return None
    base = os.path.basename(filename.replace("\\", "/"))
    return re.sub(r"[^\w.\- ]", "_", base)[:200] or None


def parser_command(
    filename: str | None, max_archive_board_bytes: int | None = None, *, bundle: bool = False
) -> list[str]:
    cmd = [sys.executable, "-I", "-B", "-m", "via_pcb.cli"]
    if bundle:
        cmd.append("--emit-bundle")
    safe = _safe_filename(filename)
    if safe:
        cmd += ["--filename", safe]
    if max_archive_board_bytes:
        cmd += ["--max-board-bytes", str(int(max_archive_board_bytes))]
    return cmd


def run_parser(
    data: bytes,
    filename: str | None,
    limits: SandboxLimits,
    *,
    command: Sequence[str] | None = None,
) -> ParseOutcome:
    """Parse ``data`` in the sandbox. ``command`` is overridable for tests only."""
    cmd = list(command) if command is not None else parser_command(filename, limits.max_archive_board_bytes)
    env = {"PATH": "/usr/local/bin:/usr/bin:/bin", "LANG": "C.UTF-8", "PYTHONHASHSEED": "0"}
    start = time.monotonic()
    with tempfile.TemporaryDirectory(prefix="via-parse-") as workdir:
        try:
            proc = subprocess.run(  # noqa: S603 - fixed argv, no shell, untrusted data only on stdin
                cmd,
                input=data,
                capture_output=True,
                timeout=limits.timeout_seconds,
                env=env,
                cwd=workdir,
                preexec_fn=_apply_limits(limits),
                start_new_session=True,
                check=False,
            )
        except subprocess.TimeoutExpired:
            return ParseOutcome(
                None,
                PARSER_TIMEOUT,
                f"Parsing took longer than {limits.timeout_seconds} seconds and was stopped.",
                time.monotonic() - start,
            )
    duration = time.monotonic() - start
    stderr = proc.stderr.decode("utf-8", "replace")[-4000:]

    if proc.returncode != 0:
        if proc.returncode in (-signal.SIGXCPU, -signal.SIGKILL) or "MemoryError" in stderr:
            logger.warning("Parser hit a resource limit (rc=%s)", proc.returncode)
            return ParseOutcome(
                None, PARSER_RESOURCE_LIMIT, "Parsing exceeded the CPU or memory limit for a single file.", duration
            )
        logger.error("Parser process failed (rc=%s): %s", proc.returncode, stderr)
        return ParseOutcome(None, PARSER_CRASHED, "The parser stopped unexpectedly while reading this file.", duration)

    try:
        payload = json.loads(proc.stdout)
        if payload.get("ok") is True:
            return ParseOutcome(PCBDesign.model_validate(payload["design"]), duration_seconds=duration)
        error = payload["error"]
        return ParseOutcome(None, str(error["code"])[:64], str(error["message"])[:2000], duration)
    except (ValueError, KeyError, TypeError, AttributeError, ValidationError) as exc:
        logger.error("Parser produced invalid output: %s", type(exc).__name__)
        return ParseOutcome(
            None, PARSER_INVALID_OUTPUT, "The parser produced an invalid result for this file.", duration
        )


@dataclass(frozen=True)
class BundleOutcome:
    bundle: bytes | None
    error_code: str | None = None
    error_message: str | None = None


def run_bundler(data: bytes, filename: str | None, limits: SandboxLimits) -> BundleOutcome:
    """Re-pack an upload as a KiCad tool bundle, in the same sandbox as the parser.

    Untrusted archives are only ever opened inside the sandbox, never in the worker itself.
    """
    cmd = parser_command(filename, limits.max_archive_board_bytes, bundle=True)
    env = {"PATH": "/usr/local/bin:/usr/bin:/bin", "LANG": "C.UTF-8", "PYTHONHASHSEED": "0"}
    with tempfile.TemporaryDirectory(prefix="via-bundle-") as workdir:
        try:
            proc = subprocess.run(  # noqa: S603 - fixed argv, untrusted data only on stdin
                cmd,
                input=data,
                capture_output=True,
                timeout=limits.timeout_seconds,
                env=env,
                cwd=workdir,
                preexec_fn=_apply_limits(limits),
                start_new_session=True,
                check=False,
            )
        except subprocess.TimeoutExpired:
            return BundleOutcome(None, PARSER_TIMEOUT, "Preparing the design for KiCad took too long.")
    if proc.returncode != 0:
        logger.error("Bundler failed (rc=%s): %s", proc.returncode, proc.stderr.decode("utf-8", "replace")[-2000:])
        return BundleOutcome(None, PARSER_CRASHED, "The design couldn't be prepared for KiCad.")
    if proc.stdout.startswith(b"PK"):
        return BundleOutcome(proc.stdout)
    try:
        error = json.loads(proc.stdout)["error"]
        return BundleOutcome(None, str(error["code"])[:64], str(error["message"])[:2000])
    except (ValueError, KeyError, TypeError):
        return BundleOutcome(None, PARSER_INVALID_OUTPUT, "The design couldn't be prepared for KiCad.")


@dataclass(frozen=True)
class ExportOutcome:
    data: bytes | None
    applied: list[int]
    refused: list[tuple[int, str]]
    board_member: str | None = None
    error_code: str | None = None
    error_message: str | None = None


def run_exporter(
    data: bytes, filename: str | None, changes: list[dict[str, object]], limits: SandboxLimits
) -> ExportOutcome:
    """Patch the original file with ``changes`` and verify it, in the same sandbox as the parser."""
    cmd = [sys.executable, "-I", "-B", "-m", "via_opt.cli"]
    header = json.dumps({"filename": _safe_filename(filename), "changes": changes}, separators=(",", ":"))
    env = {"PATH": "/usr/local/bin:/usr/bin:/bin", "LANG": "C.UTF-8", "PYTHONHASHSEED": "0"}
    with tempfile.TemporaryDirectory(prefix="via-export-") as workdir:
        try:
            proc = subprocess.run(  # noqa: S603 - fixed argv, untrusted data only on stdin
                cmd,
                input=header.encode() + b"\n" + data,
                capture_output=True,
                timeout=limits.timeout_seconds,
                env=env,
                cwd=workdir,
                preexec_fn=_apply_limits(limits),
                start_new_session=True,
                check=False,
            )
        except subprocess.TimeoutExpired:
            return ExportOutcome(None, [], [], None, PARSER_TIMEOUT, "Exporting took too long and was stopped.")
    if proc.returncode != 0:
        logger.error("Exporter failed (rc=%s): %s", proc.returncode, proc.stderr.decode("utf-8", "replace")[-2000:])
        if proc.returncode in (-signal.SIGXCPU, -signal.SIGKILL):
            return ExportOutcome(
                None, [], [], None, PARSER_RESOURCE_LIMIT, "Exporting exceeded the CPU or memory limit."
            )
        return ExportOutcome(None, [], [], None, PARSER_CRASHED, "The exporter stopped unexpectedly.")
    out = proc.stdout
    try:
        if out.startswith(b"VIAX"):
            meta_line, _, body = out[4:].partition(b"\n")
            meta = json.loads(meta_line)
            refused = [(int(i), str(r)) for i, r in meta["refused"]]
            return ExportOutcome(body, [int(i) for i in meta["applied"]], refused, meta.get("board_member"))
        error = json.loads(out)["error"]
        return ExportOutcome(None, [], [], None, str(error["code"])[:64], str(error["message"])[:2000])
    except (ValueError, KeyError, TypeError):
        return ExportOutcome(None, [], [], None, PARSER_INVALID_OUTPUT, "The exporter produced an invalid result.")
