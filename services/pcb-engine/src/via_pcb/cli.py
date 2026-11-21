"""Parse one PCB file from stdin and write the result as JSON to stdout.

This is the entry point VIA runs inside the constrained parser subprocess
(``python -I -B -m via_pcb.cli --filename board.kicad_pcb < board``). It has no
network, database or storage access and reads nothing but stdin.

Output (always a single JSON object on stdout, exit code 0 unless the process
itself fails)::

    {"ok": true, "design": {...PCBDesign...}}
    {"ok": false, "error": {"code": "unsupported_format", "message": "..."}}

It also works as a developer tool::

    python -m via_pcb.cli --filename board.kicad_pcb --summary < board.kicad_pcb
"""

from __future__ import annotations

import argparse
import json
import sys

from via_pcb.adapters import AdapterNotFoundError, UnsupportedFormatError, parse_pcb

#: Hard ceiling on input read from stdin (the API enforces its own, lower limit).
MAX_INPUT_BYTES = 512 * 1024 * 1024


def _emit(payload: dict[str, object]) -> None:
    sys.stdout.write(json.dumps(payload, separators=(",", ":")))
    sys.stdout.flush()


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="via_pcb.cli", description=__doc__.splitlines()[0])
    parser.add_argument("--filename", default=None, help="original file name (used for format detection)")
    parser.add_argument("--summary", action="store_true", help="print only source info, stats and warnings")
    args = parser.parse_args(argv)

    data = sys.stdin.buffer.read(MAX_INPUT_BYTES + 1)
    if len(data) > MAX_INPUT_BYTES:
        _emit({"ok": False, "error": {"code": "file_too_large", "message": "Input exceeds the parser limit."}})
        return 0
    try:
        design = parse_pcb(data, filename=args.filename)
    except AdapterNotFoundError as exc:
        _emit({"ok": False, "error": {"code": "unsupported_format", "message": str(exc)}})
        return 0
    except UnsupportedFormatError as exc:
        _emit({"ok": False, "error": {"code": "invalid_file", "message": str(exc)}})
        return 0
    except RecursionError:
        _emit({"ok": False, "error": {"code": "invalid_file", "message": "File structure is too deeply nested."}})
        return 0

    payload = design.model_dump(mode="json")
    if args.summary:
        payload = {k: payload[k] for k in ("source", "title", "stats", "warnings")}
    _emit({"ok": True, "design": payload})
    return 0


if __name__ == "__main__":
    sys.exit(main())
