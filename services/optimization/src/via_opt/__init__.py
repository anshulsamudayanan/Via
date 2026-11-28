"""VIA Optimize: explicit, validated, comparable design-change candidates.

See docs/OPTIMIZATION_ENGINE.md. Nothing here modifies the original design.
"""

from via_opt.candidates import Candidate, CandidateStatus, Score, Validation, ValidationStatus
from via_opt.changes import EXPORTABLE, Change, ChangeKind, Target, apply
from via_opt.comparison import dominates, pareto_front
from via_opt.constraints import Constraints, Requirement
from via_opt.engine import OPTIMIZER_VERSION, OptimizationResult, optimize
from via_opt.lifecycle import lifecycle
from via_opt.modules import MODULES, ModuleSpec
from via_opt.objectives import METRIC_FOR, Objective, metrics
from via_opt.rules import ConstraintResult, ConstraintStatus

__all__ = [
    "EXPORTABLE",
    "METRIC_FOR",
    "MODULES",
    "OPTIMIZER_VERSION",
    "Candidate",
    "CandidateStatus",
    "Change",
    "ChangeKind",
    "ConstraintResult",
    "ConstraintStatus",
    "Constraints",
    "ModuleSpec",
    "Objective",
    "OptimizationResult",
    "Requirement",
    "Score",
    "Target",
    "Validation",
    "ValidationStatus",
    "apply",
    "dominates",
    "lifecycle",
    "metrics",
    "optimize",
    "pareto_front",
]
