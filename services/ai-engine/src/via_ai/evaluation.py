"""Evaluation harness: run AI features over cases and measure how often outputs pass verification.

Used in tests with :class:`~via_ai.providers.scripted.ScriptedProvider` (deterministic), and
runnable against a real provider by an operator who has configured one and has consent for the
projects in the cases. It measures grounding (references and numbers exist in the context), not
engineering correctness, which needs human review.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from via_ai.context import ProjectContext
from via_ai.orchestration import explain, review
from via_ai.providers import AIError, AIProvider


@dataclass(frozen=True)
class Case:
    name: str
    context: ProjectContext
    question: str | None = None  # None = design review


@dataclass
class EvalReport:
    total: int = 0
    accepted: int = 0
    rejected: int = 0
    errors: int = 0
    problems: dict[str, list[str]] = field(default_factory=dict)

    @property
    def acceptance_rate(self) -> float:
        return self.accepted / self.total if self.total else 0.0


def evaluate(provider: AIProvider, cases: list[Case]) -> EvalReport:
    report = EvalReport()
    for case in cases:
        report.total += 1
        try:
            result = explain(provider, case.context, case.question) if case.question else review(provider, case.context)
        except AIError as exc:
            report.errors += 1
            report.problems[case.name] = [f"{type(exc).__name__}: {exc}"]
            continue
        if result.accepted:
            report.accepted += 1
        else:
            report.rejected += 1
            report.problems[case.name] = result.report.problems
    return report
