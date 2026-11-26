"""What a check sees: the design plus indexes built once per analysis run."""

from __future__ import annotations

from dataclasses import dataclass, field
from functools import cached_property
from typing import Any

from via_pcb.models import Component, Pad, PCBDesign


@dataclass
class AnalysisContext:
    design: PCBDesign
    #: Per-run options (e.g. a manufacturing profile from Milestone 3). Checks read only keys they own.
    options: dict[str, Any] = field(default_factory=dict)

    @cached_property
    def components_by_id(self) -> dict[str, Component]:
        return {c.id: c for c in self.design.components if c.id}

    @cached_property
    def pads_with_component(self) -> list[tuple[Component, Pad]]:
        return [(c, p) for c in self.design.components for p in c.pads]

    @cached_property
    def copper_layers(self) -> set[str]:
        return {layer.name for layer in self.design.layers if layer.kind == "copper"}

    @property
    def kicad_file_version(self) -> int | None:
        v = self.design.source.format_version
        return int(v) if self.design.source.format == "kicad" and v and v.isdigit() else None
