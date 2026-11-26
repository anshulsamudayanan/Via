"""Export a change set from stdin, inside VIA's parser sandbox.

Input on stdin: one line of JSON ``{"filename": ..., "changes": [...Change...]}``, then the original
file's bytes (a board or a KiCad project archive). It reads nothing else and has no network,
database or storage access.

Output on stdout:

* success: ``VIAX`` + one line of JSON ``{"ok": true, "applied": [...], "refused": [[i, reason]], "board_member": ...}``
  + ``\\n`` + the exported file's bytes;
* failure: one JSON object ``{"ok": false, "error": {"code": ..., "message": ...}}``.
"""

from __future__ import annotations

import json
import sys

from pydantic import ValidationError

from via_opt.changes import Change
from via_opt.export import ExportVerificationError, export_changes
from via_pcb.adapters import UnsupportedFormatError

MAGIC = b"VIAX"
MAX_INPUT_BYTES = 512 * 1024 * 1024


def _fail(code: str, message: str) -> int:
    sys.stdout.write(json.dumps({"ok": False, "error": {"code": code, "message": message}}))
    sys.stdout.flush()
    return 0


def main() -> int:
    raw = sys.stdin.buffer.read(MAX_INPUT_BYTES + 1)
    if len(raw) > MAX_INPUT_BYTES:
        return _fail("file_too_large", "Input exceeds the exporter limit.")
    header, sep, data = raw.partition(b"\n")
    try:
        spec = json.loads(header) if sep else None
        if not isinstance(spec, dict):
            raise ValueError("missing header")
        changes = [Change.model_validate(c) for c in spec.get("changes", [])]
        filename = spec.get("filename")
    except (ValueError, ValidationError):
        return _fail("invalid_request", "The export request was malformed.")
    try:
        result = export_changes(data, filename if isinstance(filename, str) else None, changes)
    except ExportVerificationError as exc:
        return _fail("export_verification_failed", f"The patched file didn't match the changes: {exc}")
    except (UnsupportedFormatError, UnicodeDecodeError, ValueError) as exc:
        return _fail("export_unsupported", str(exc)[:500] or "This file can't be patched.")
    except RecursionError:
        return _fail("invalid_file", "File structure is too deeply nested.")
    meta = {"ok": True, "applied": result.applied, "refused": result.refused, "board_member": result.board_member}
    sys.stdout.buffer.write(MAGIC + json.dumps(meta, separators=(",", ":")).encode() + b"\n" + result.data)
    sys.stdout.flush()
    return 0


if __name__ == "__main__":
    sys.exit(main())
