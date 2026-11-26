"""Client for the internal KiCad tool service (``services/eda-runner``) and the worker-side DRC step.

The worker already holds the uploaded file; it re-packs it in the parser sandbox (fixed names,
only board + project rule files) and sends that bundle to the service, which has no credentials
and sits on an internal-only network. KiCad's JSON report comes back and becomes findings via the
``kicad_drc`` check. If the service isn't configured or fails, the check is skipped with the reason.
"""

from __future__ import annotations

import hashlib
import json
import logging
import urllib.error
import urllib.request
from typing import Any

from sqlalchemy.orm import Session

from via_api.config import Settings
from via_api.models import DesignRevision
from via_api.parsing.importer import source_file
from via_api.parsing.sandbox import SandboxLimits, run_bundler
from via_api.storage import ObjectNotFoundError, StorageBackend, StorageError

logger = logging.getLogger("via_api.eda")


class EdaUnavailable(Exception):
    """The service couldn't be reached or answered with an unusable response."""


class EdaClient:
    def __init__(self, base_url: str, timeout_seconds: float) -> None:
        self.base_url = base_url.rstrip("/")
        self.timeout = timeout_seconds

    def drc(self, bundle: bytes) -> dict[str, Any]:
        req = urllib.request.Request(  # noqa: S310 - internal service URL from settings
            f"{self.base_url}/drc",
            data=bundle,
            method="POST",
            headers={"Content-Type": "application/zip", "Content-Length": str(len(bundle))},
        )
        try:
            with urllib.request.urlopen(req, timeout=self.timeout) as resp:  # noqa: S310
                body = resp.read()
        except urllib.error.HTTPError as exc:
            with exc:
                try:
                    payload = json.loads(exc.read())
                except ValueError:
                    payload = {}
            message = payload.get("error", {}).get("message") if isinstance(payload, dict) else None
            raise EdaUnavailable(message or f"KiCad service answered HTTP {exc.code}.") from exc
        except (urllib.error.URLError, TimeoutError, OSError) as exc:
            raise EdaUnavailable("The KiCad service couldn't be reached.") from exc
        try:
            payload = json.loads(body)
        except ValueError as exc:
            raise EdaUnavailable("The KiCad service returned an invalid response.") from exc
        if not isinstance(payload, dict):
            raise EdaUnavailable("The KiCad service returned an invalid response.")
        return payload


def kicad_drc_input(
    db: Session, storage: StorageBackend, revision: DesignRevision, settings: Settings, limits: SandboxLimits
) -> dict[str, Any]:
    """What the ``kicad_drc`` check needs: ``{report, rules, kicad_version, duration_seconds}`` or ``{error}``."""
    if not settings.eda_url:
        return {"error": "KiCad DRC isn't configured on this server (VIA_EDA_URL is not set)."}
    source = source_file(db, revision)
    try:
        if source is None:
            raise ObjectNotFoundError("source row missing")
        data = storage.get(source.storage_key)
    except (ObjectNotFoundError, StorageError):
        return {"error": "The uploaded file couldn't be read from storage."}
    if hashlib.sha256(data).hexdigest() != revision.source_sha256:
        return {"error": "The stored file doesn't match the upload."}
    bundled = run_bundler(data, source.original_filename, limits)
    if bundled.bundle is None:
        return {"error": bundled.error_message or "The design couldn't be prepared for KiCad."}
    try:
        payload = EdaClient(settings.eda_url, settings.eda_timeout_seconds).drc(bundled.bundle)
    except EdaUnavailable as exc:
        logger.warning("KiCad DRC unavailable for revision %s: %s", revision.id, exc)
        return {"error": str(exc)}
    if not payload.get("ok"):
        error = payload.get("error") or {}
        return {"error": str(error.get("message") or "KiCad DRC failed.")[:500]}
    report = payload.get("report")
    if not isinstance(report, dict):
        return {"error": "KiCad DRC returned no report."}
    return {
        "report": report,
        "rules": payload.get("rules", "defaults"),
        "kicad_version": payload.get("kicad_version"),
        "duration_seconds": payload.get("duration_seconds"),
    }
