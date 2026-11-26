"""Runs registered checks on a design and collects their findings.

A failing check never fails the whole analysis: its exception is recorded as an
``error`` check run (type only, no stack trace in results) and the other checks continue.
"""

from __future__ import annotations

import logging
import time
from enum import StrEnum

from pydantic import BaseModel, ConfigDict, Field

from via_pcb.analysis.context import AnalysisContext
from via_pcb.analysis.findings import Finding
from via_pcb.analysis.registry import CheckRegistry
from via_pcb.models import ENGINE_VERSION, PCBDesign

logger = logging.getLogger("via_pcb.analysis")

#: Version of the analysis framework itself (finding schema, engine behaviour).
ANALYSIS_VERSION = "1.0.0"


class CheckStatus(StrEnum):
    OK = "ok"
    SKIPPED = "skipped"
    ERROR = "error"


class CheckRun(BaseModel):
    model_config = ConfigDict(extra="forbid")

    check_id: str
    version: str
    status: CheckStatus
    finding_count: int = 0
    duration_ms: float = 0.0
    message: str | None = Field(default=None, description="Skip reason or error type")


class AnalysisResult(BaseModel):
    model_config = ConfigDict(extra="forbid")

    analysis_version: str = ANALYSIS_VERSION
    engine_version: str = ENGINE_VERSION
    design_schema_version: str
    design_engine_version: str
    checks: list[CheckRun]
    findings: list[Finding]


class AnalysisEngine:
    def __init__(self, registry: CheckRegistry) -> None:
        self.registry = registry

    def run(self, design: PCBDesign, options: dict | None = None, only: set[str] | None = None) -> AnalysisResult:
        ctx = AnalysisContext(design=design, options=dict(options or {}))
        runs: list[CheckRun] = []
        findings: list[Finding] = []
        for check in self.registry.all():
            if only is not None and check.id not in only:
                continue
            started = time.perf_counter()
            reason = check.skip_reason(ctx)
            if reason:
                runs.append(
                    CheckRun(check_id=check.id, version=check.version, status=CheckStatus.SKIPPED, message=reason)
                )
                continue
            try:
                produced = list(check.run(ctx))
                for f in produced:
                    if f.check_id != check.id or f.source != check.source:
                        raise ValueError(f"finding attributed to {f.check_id}/{f.source}")
            except Exception as exc:  # isolate check failures (including misattributed findings)
                logger.exception("Check %s failed", check.id)
                runs.append(
                    CheckRun(
                        check_id=check.id,
                        version=check.version,
                        status=CheckStatus.ERROR,
                        duration_ms=round((time.perf_counter() - started) * 1000, 2),
                        message=type(exc).__name__,
                    )
                )
                continue
            for f in produced:
                if not f.fingerprint:
                    f.with_fingerprint()
            findings.extend(produced)
            runs.append(
                CheckRun(
                    check_id=check.id,
                    version=check.version,
                    status=CheckStatus.OK,
                    finding_count=len(produced),
                    duration_ms=round((time.perf_counter() - started) * 1000, 2),
                )
            )
        findings.sort(key=lambda f: (f.severity.rank, f.category, f.title))
        return AnalysisResult(
            design_schema_version=design.schema_version,
            design_engine_version=design.engine_version,
            checks=runs,
            findings=findings,
        )
