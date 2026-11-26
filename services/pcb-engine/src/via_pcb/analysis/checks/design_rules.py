"""Whether the project's design rules are available (exact)."""

from __future__ import annotations

from collections.abc import Iterable

from via_pcb.analysis.context import AnalysisContext
from via_pcb.analysis.findings import Category, Evidence, Finding, Severity
from via_pcb.analysis.registry import Check

#: KiCad 5's file version. Newer formats keep design rules in the .kicad_pro project file.
KICAD5_FILE_VERSION = 20171130


class DesignRulesSourceCheck(Check):
    id = "design_rules_source"
    version = "1.0.0"
    category = Category.DESIGN_RULES
    title = "Design rules available"
    description = "Rule-based checks need the project's own rules; KiCad 6+ stores them in the .kicad_pro file."

    def skip_reason(self, ctx: AnalysisContext) -> str | None:
        if ctx.design.source.format != "kicad":
            return "Only applies to KiCad designs."
        return None

    def run(self, ctx: AnalysisContext) -> Iterable[Finding]:
        c = ctx.design.constraints
        version = ctx.kicad_file_version
        if c.rules_source == "project_file" or (version is not None and version <= KICAD5_FILE_VERSION):
            return
        yield Finding(
            check_id=self.id,
            rule="project_rules_missing",
            category=self.category,
            severity=Severity.INFO,
            title="Project design rules not imported",
            description=(
                "Only the board file was uploaded. Its design rules and net classes live in the project's "
                ".kicad_pro file, so rule-based checks fall back to defaults."
            ),
            explanation=(
                "Clearance, track-width and via checks compare the board against the designer's rules. With "
                "defaults instead, results can include violations that don't exist and miss ones that do."
            ),
            evidence=[
                Evidence(kind="source_data", label="Rules source", value="board file only"),
                Evidence(kind="source_data", label="KiCad file version", value=str(version or "unknown")),
            ],
            suggested_resolution="Upload the KiCad project as a .zip (board plus .kicad_pro and .kicad_dru).",
        ).with_fingerprint("rules")
