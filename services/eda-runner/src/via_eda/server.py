"""Internal HTTP API (standard library only).

    GET  /health  -> {"status": "ok", "kicad_version": "9.0.6"}
    POST /drc     body: bundle zip (board.kicad_pcb [+ board.kicad_pro, board.kicad_dru])
                  -> {"ok": true, "report": {...KiCad JSON...}, "rules": "project_file"|"defaults", ...}
                  -> {"ok": false, "error": {"code", "message"}}

Only reachable on Compose's internal ``eda`` network. Settings (environment):
VIA_EDA_PORT (8100), VIA_EDA_CONCURRENCY (2), VIA_EDA_TIMEOUT_SECONDS (120),
VIA_EDA_MEMORY_LIMIT_MB (4096), VIA_EDA_MAX_BODY_BYTES (64 MiB), VIA_EDA_KICAD_CLI (kicad-cli).
"""

from __future__ import annotations

import json
import logging
import os
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from typing import Any

from via_eda import __version__
from via_eda.drc import BundleError, Limits, kicad_version, read_bundle, run_drc

logger = logging.getLogger("via_eda")


class Config:
    def __init__(self, env: dict[str, str] | None = None) -> None:
        env = dict(os.environ if env is None else env)
        self.port = int(env.get("VIA_EDA_PORT", "8100"))
        self.concurrency = int(env.get("VIA_EDA_CONCURRENCY", "2"))
        self.max_body = int(env.get("VIA_EDA_MAX_BODY_BYTES", str(64 * 1024**2)))
        self.kicad_cli = env.get("VIA_EDA_KICAD_CLI", "kicad-cli")
        self.limits = Limits(
            timeout_seconds=int(env.get("VIA_EDA_TIMEOUT_SECONDS", "120")),
            memory_bytes=int(env.get("VIA_EDA_MEMORY_LIMIT_MB", "4096")) * 1024**2,
            max_member_bytes=self.max_body,
        )


def make_handler(config: Config) -> type[BaseHTTPRequestHandler]:
    slots = threading.BoundedSemaphore(config.concurrency)
    version: dict[str, str | None] = {}

    class Handler(BaseHTTPRequestHandler):
        server_version = f"via-eda/{__version__}"

        def log_message(self, fmt: str, *args: Any) -> None:  # route through logging
            logger.info("%s %s", self.address_string(), fmt % args)

        def _send(self, status: int, payload: dict[str, Any]) -> None:
            body = json.dumps(payload, separators=(",", ":")).encode()
            self.send_response(status)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        def do_GET(self) -> None:
            if self.path != "/health":
                self._send(404, {"error": "not_found"})
                return
            if "kicad" not in version:
                version["kicad"] = kicad_version(config.kicad_cli)
            ok = version["kicad"] is not None
            self._send(200 if ok else 503, {"status": "ok" if ok else "error", "kicad_version": version["kicad"]})

        def do_POST(self) -> None:
            if self.path != "/drc":
                self._send(404, {"error": "not_found"})
                return
            try:
                length = int(self.headers.get("Content-Length", ""))
            except ValueError:
                self._send(
                    411, {"ok": False, "error": {"code": "length_required", "message": "Content-Length required."}}
                )
                return
            if length <= 0 or length > config.max_body:
                self._send(413, {"ok": False, "error": {"code": "too_large", "message": "Bundle too large."}})
                return
            data = self.rfile.read(length)
            if not slots.acquire(blocking=False):
                self._send(503, {"ok": False, "error": {"code": "busy", "message": "KiCad DRC is busy; retry later."}})
                return
            try:
                try:
                    files = read_bundle(data, config.limits)
                except BundleError as exc:
                    self._send(400, {"ok": False, "error": {"code": "invalid_bundle", "message": str(exc)}})
                    return
                result = run_drc(files, config.limits, config.kicad_cli)
                payload = result.to_json()
                if "kicad" not in version:
                    version["kicad"] = kicad_version(config.kicad_cli)
                payload["kicad_version"] = version["kicad"]
                self._send(200, payload)
            finally:
                slots.release()

    return Handler


def serve(config: Config | None = None) -> None:
    config = config or Config()
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s %(message)s")
    server = ThreadingHTTPServer(("0.0.0.0", config.port), make_handler(config))  # noqa: S104 - internal network
    logger.info("via-eda %s listening on :%d", __version__, config.port)
    server.serve_forever()


if __name__ == "__main__":
    serve()
