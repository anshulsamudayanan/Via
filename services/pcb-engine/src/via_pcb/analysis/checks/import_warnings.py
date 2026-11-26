"""Things the parser skipped or found suspicious, surfaced as findings (exact)."""

from __future__ import annotations

from collections.abc import Iterable

from via_pcb.analysis.context import AnalysisContext
from via_pcb.analysis.findings import Category, Evidence, Finding, Severity
from via_pcb.analysis.registry import Check

#: Warnings another check reports with more detail.
_COVERED_ELSEWHERE = {"missing_outline", "open_outline", "missing_project_file"}
#: Warnings that mean design data was skipped (analysis may be incomplete).
_DATA_SKIPPED = {"invalid_track", "invalid_zone", "unsupported_curve", "unsupported_object", "unknown_pad_type"}


class ImportWarningsCheck(Check):
    id = "import_warnings"
    version = "1.0.0"
    category = Category.IMPORT
    title = "Import warnings"
    description = "Data the parser skipped or found suspicious, which can make other results incomplete."

    def run(self, ctx: AnalysisContext) -> Iterable[Finding]:
        for w in ctx.design.warnings:
            if w.code in _COVERED_ELSEWHERE:
                continue
            skipped = w.code in _DATA_SKIPPED
            yield Finding(
                check_id=self.id,
                rule=w.code,
                category=self.category,
                severity=Severity.LOW if skipped else Severity.INFO,
                title="Design data skipped during import" if skipped else "Import note",
                description=w.message,
                explanation=(
                    "This part of the file wasn't converted into VIA's model, so checks that depend on it can't see it."
                    if skipped
                    else "Something about the file was unusual; results remain valid but may need a closer look."
                ),
                evidence=[Evidence(kind="tool_output", label="Parser warning", value=f"{w.code}: {w.message}")],
            ).with_fingerprint(w.code, w.message)
