#!/usr/bin/env python3
"""Download the pinned real KiCad boards (and their project files) listed in tests/engineering/real_fixtures.json.

The files are CC BY-SA 4.0 (KiCad demo projects). They are used only for internal
validation, stored in the git-ignored tests/engineering/real/ folder and never committed.
Each download is checked against its pinned SHA-256.

Usage: python scripts/fetch_real_fixtures.py
"""

from __future__ import annotations

import hashlib
import json
import sys
import urllib.parse
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
MANIFEST = ROOT / "tests" / "engineering" / "real_fixtures.json"
DEST = ROOT / "tests" / "engineering" / "real"
API = "https://gitlab.com/api/v4/projects/kicad%2Fcode%2Fkicad/repository/files/{path}/raw?ref={ref}"


def main() -> int:
    manifest = json.loads(MANIFEST.read_text())
    DEST.mkdir(parents=True, exist_ok=True)
    failures = 0
    for fx in manifest["fixtures"]:
        target = DEST / fx["file"]
        if target.exists() and hashlib.sha256(target.read_bytes()).hexdigest() == fx["sha256"]:
            print(f"ok      {fx['file']}")
            continue
        ext = fx.get("source_ext", ".kicad_pcb")
        path = urllib.parse.quote(f"demos/{fx['project']}/{fx['project']}{ext}", safe="")
        url = API.format(path=path, ref=urllib.parse.quote(fx["kicad_tag"]))
        with urllib.request.urlopen(url, timeout=60) as resp:  # noqa: S310 - fixed https URL
            data = resp.read()
        digest = hashlib.sha256(data).hexdigest()
        if digest != fx["sha256"]:
            print(f"FAILED  {fx['file']}: sha256 {digest} != pinned {fx['sha256']}", file=sys.stderr)
            failures += 1
            continue
        target.write_bytes(data)
        print(f"fetched {fx['file']} ({len(data)} bytes)")
    return 1 if failures else 0


if __name__ == "__main__":
    sys.exit(main())
