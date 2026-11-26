"""VIA's PCB analysis engine: checks that turn a normalized design into structured findings.

Usage::

    from via_pcb.analysis import default_engine

    result = default_engine().run(design)
    for finding in result.findings: ...

See docs/FINDINGS_SYSTEM.md and docs/PCB_ANALYSIS.md.
"""

from via_pcb.analysis.context import AnalysisContext
from via_pcb.analysis.engine import ANALYSIS_VERSION, AnalysisEngine, AnalysisResult, CheckRun, CheckStatus
from via_pcb.analysis.findings import (
    Category,
    Evidence,
    Finding,
    ObjectKind,
    ObjectRef,
    Region,
    Severity,
    Source,
    Verification,
)
from via_pcb.analysis.registry import Check, CheckRegistry


def default_registry() -> CheckRegistry:
    from via_pcb.analysis.checks.board_outline import BoardOutlineCheck
    from via_pcb.analysis.checks.connectivity import (
        CopperIslandsCheck,
        CopperLayerUsageCheck,
        PadsWithoutNetCheck,
        SinglePadNetsCheck,
    )
    from via_pcb.analysis.checks.design_rules import DesignRulesSourceCheck
    from via_pcb.analysis.checks.import_warnings import ImportWarningsCheck
    from via_pcb.analysis.checks.kicad_drc import KiCadDrcCheck
    from via_pcb.analysis.checks.manufacturing import MANUFACTURING_CHECKS
    from via_pcb.analysis.checks.placement import PLACEMENT_CHECKS
    from via_pcb.analysis.checks.routing import ROUTING_CHECKS

    registry = CheckRegistry()
    for check in (
        KiCadDrcCheck(),
        BoardOutlineCheck(),
        DesignRulesSourceCheck(),
        PadsWithoutNetCheck(),
        CopperIslandsCheck(),
        SinglePadNetsCheck(),
        CopperLayerUsageCheck(),
        *(cls() for cls in MANUFACTURING_CHECKS),
        *(cls() for cls in PLACEMENT_CHECKS),
        *(cls() for cls in ROUTING_CHECKS),
        ImportWarningsCheck(),
    ):
        registry.register(check)
    return registry


def default_engine() -> AnalysisEngine:
    return AnalysisEngine(default_registry())


__all__ = [
    "ANALYSIS_VERSION",
    "AnalysisContext",
    "AnalysisEngine",
    "AnalysisResult",
    "Category",
    "Check",
    "CheckRegistry",
    "CheckRun",
    "CheckStatus",
    "Evidence",
    "Finding",
    "ObjectKind",
    "ObjectRef",
    "Region",
    "Severity",
    "Source",
    "Verification",
    "default_engine",
    "default_registry",
]
