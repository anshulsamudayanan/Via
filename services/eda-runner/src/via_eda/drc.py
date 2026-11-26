"""Run ``kicad-cli pcb drc`` on a bundle, under resource limits, in a throwaway directory."""

from __future__ import annotations

import io
import json
import logging
import os
import shutil
import signal
import subprocess
import tempfile
import time
import zipfile
from dataclasses import dataclass, field
from typing import Any

logger = logging.getLogger("via_eda.drc")

#: The only members a bundle may contain (fixed names, so nothing user-controlled reaches the filesystem).
BOARD, PROJECT, RULES = "board.kicad_pcb", "board.kicad_pro", "board.kicad_dru"
ALLOWED = (BOARD, PROJECT, RULES)


class BundleError(ValueError):
    """The request body isn't a valid bundle."""


@dataclass(frozen=True)
class Limits:
    timeout_seconds: int = 120
    memory_bytes: int = 4 * 1024**3
    max_member_bytes: int = 64 * 1024**2
    max_report_bytes: int = 256 * 1024**2


@dataclass
class DrcResult:
    ok: bool
    report: dict[str, Any] | None = None
    error_code: str | None = None
    error_message: str | None = None
    duration_seconds: float = 0.0
    rules: str = "defaults"  # "project_file" when board.kicad_pro was supplied
    meta: dict[str, Any] = field(default_factory=dict)

    def to_json(self) -> dict[str, Any]:
        if self.ok:
            return {"ok": True, "report": self.report, "rules": self.rules, "duration_seconds": self.duration_seconds}
        return {"ok": False, "error": {"code": self.error_code, "message": self.error_message}}


def read_bundle(data: bytes, limits: Limits) -> dict[str, bytes]:
    try:
        zf = zipfile.ZipFile(io.BytesIO(data))
    except (zipfile.BadZipFile, ValueError) as exc:
        raise BundleError("The bundle isn't a valid zip.") from exc
    files: dict[str, bytes] = {}
    with zf:
        infos = zf.infolist()
        if len(infos) > len(ALLOWED):
            raise BundleError("The bundle has unexpected members.")
        for info in infos:
            if info.filename not in ALLOWED or info.filename in files:
                raise BundleError(f"Unexpected bundle member: {info.filename[:80]!r}")
            if info.flag_bits & 0x1 or info.file_size > limits.max_member_bytes:
                raise BundleError(f"Bundle member {info.filename} is encrypted or too large.")
            with zf.open(info) as fh:
                content = fh.read(limits.max_member_bytes + 1)
            if len(content) > limits.max_member_bytes:
                raise BundleError(f"Bundle member {info.filename} is too large.")
            files[info.filename] = content
    if BOARD not in files:
        raise BundleError("The bundle has no board.")
    return files


#: Applies resource limits with the shell's ulimit, then execs the command. (Not preexec_fn:
#: the server is multi-threaded, and running Python code between fork and exec can deadlock.)
_LIMITED = 'ulimit -t "$1"; ulimit -v "$2"; ulimit -f "$3"; ulimit -c 0; shift 3; exec "$@"'


def limited(cmd: list[str], limits: Limits) -> list[str]:
    return [
        "/bin/sh", "-c", _LIMITED, "via-drc",
        str(limits.timeout_seconds),
        str(limits.memory_bytes // 1024),  # KiB
        str(limits.max_report_bytes // 512),  # 512-byte blocks
        *cmd,
    ]  # fmt: skip


def run_drc(files: dict[str, bytes], limits: Limits, kicad_cli: str = "kicad-cli") -> DrcResult:
    started = time.monotonic()
    workdir = tempfile.mkdtemp(prefix="via-drc-")
    try:
        for name, content in files.items():
            with open(os.path.join(workdir, name), "wb") as fh:
                fh.write(content)
        report_path = os.path.join(workdir, "report.json")
        cmd = [
            kicad_cli, "pcb", "drc", "--format", "json", "--units", "mm",
            # Errors and warnings; violations the designer excluded in KiCad stay excluded.
            "--severity-error", "--severity-warning",
            "--output", report_path, os.path.join(workdir, BOARD),
        ]  # fmt: skip
        # Minimal environment: KiCad needs a writable HOME for its settings; nothing else is passed.
        env = {"HOME": workdir, "PATH": os.environ.get("PATH", "/usr/bin:/bin"), "LANG": "C.UTF-8"}
        proc = subprocess.Popen(  # noqa: S603 - fixed argv; the shell script is a constant
            limited(cmd, limits),
            cwd=workdir,
            env=env,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            start_new_session=True,
        )
        try:
            _out, err = proc.communicate(timeout=limits.timeout_seconds + 5)
        except subprocess.TimeoutExpired:
            os.killpg(proc.pid, signal.SIGKILL)
            proc.communicate()
            return DrcResult(False, error_code="timeout", error_message="KiCad DRC took too long and was stopped.")
        duration = round(time.monotonic() - started, 3)
        if proc.returncode != 0 or not os.path.exists(report_path):
            logger.warning("kicad-cli exited %s: %s", proc.returncode, err.decode(errors="replace")[-2000:])
            killed = proc.returncode is not None and proc.returncode < 0
            message = "KiCad DRC ran out of time or memory." if killed else "KiCad couldn't load or check this board."
            return DrcResult(False, error_code="drc_failed", error_message=message, duration_seconds=duration)
        with open(report_path, "rb") as fh:
            report = json.loads(fh.read())
        return DrcResult(
            True,
            report=report,
            duration_seconds=duration,
            rules="project_file" if PROJECT in files else "defaults",
        )
    finally:
        shutil.rmtree(workdir, ignore_errors=True)


def kicad_version(kicad_cli: str = "kicad-cli") -> str | None:
    try:
        out = subprocess.run(  # noqa: S603
            [kicad_cli, "version"],
            capture_output=True,
            timeout=30,
            check=True,
            env={"HOME": tempfile.gettempdir(), "PATH": os.environ.get("PATH", "")},
        ).stdout
    except (OSError, subprocess.SubprocessError):
        return None
    return out.decode(errors="replace").strip() or None
