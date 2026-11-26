"""Check contract and registry."""

from __future__ import annotations

from abc import ABC, abstractmethod
from collections.abc import Iterable
from typing import ClassVar

from via_pcb.analysis.context import AnalysisContext
from via_pcb.analysis.findings import Category, Finding, Source


class Check(ABC):
    """One analysis check. Stateless; ``run`` yields findings for one design.

    Bump ``version`` whenever the check's logic or thresholds change, so stored results
    say exactly which logic produced them.
    """

    id: ClassVar[str]
    version: ClassVar[str]
    category: ClassVar[Category]
    title: ClassVar[str]
    description: ClassVar[str]
    source: ClassVar[Source] = Source.VIA_DETERMINISTIC

    def skip_reason(self, ctx: AnalysisContext) -> str | None:
        """Return why the check can't run on this design (shown to the user), or None to run it."""
        return None

    @abstractmethod
    def run(self, ctx: AnalysisContext) -> Iterable[Finding]: ...


class CheckRegistry:
    def __init__(self) -> None:
        self._checks: dict[str, Check] = {}

    def register(self, check: Check) -> None:
        if check.id in self._checks:
            raise ValueError(f"Check '{check.id}' already registered")
        self._checks[check.id] = check

    def get(self, check_id: str) -> Check:
        return self._checks[check_id]

    def all(self) -> list[Check]:
        return list(self._checks.values())
