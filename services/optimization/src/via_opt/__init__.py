"""VIA Optimize: explicit, validated, comparable design-change candidates.

See docs/OPTIMIZATION_ENGINE.md. Nothing here modifies the original design.
"""

from via_opt.candidates import Candidate, CandidateStatus, Validation, ValidationStatus
from via_opt.changes import EXPORTABLE, Change, ChangeKind, Target, apply
from via_opt.comparison import dominates, pareto_front
from via_opt.constraints import Constraints
from via_opt.engine import OPTIMIZER_VERSION, OptimizationResult, optimize
from via_opt.objectives import METRIC_FOR, Objective, metrics

__all__ = [
    "EXPORTABLE",
    "METRIC_FOR",
    "OPTIMIZER_VERSION",
    "Candidate",
    "CandidateStatus",
    "Change",
    "ChangeKind",
    "Constraints",
    "Objective",
    "OptimizationResult",
    "Target",
    "Validation",
    "ValidationStatus",
    "apply",
    "dominates",
    "metrics",
    "optimize",
    "pareto_front",
]
