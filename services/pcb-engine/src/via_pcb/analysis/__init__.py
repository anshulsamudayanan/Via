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
    from via_pcb.analysis.checks.connectivity import PadsWithoutNetCheck
    from via_pcb.analysis.checks.design_rules import DesignRulesSourceCheck
    from via_pcb.analysis.checks.import_warnings import ImportWarningsCheck

    registry = CheckRegistry()
    for check in (BoardOutlineCheck(), DesignRulesSourceCheck(), PadsWithoutNetCheck(), ImportWarningsCheck()):
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
