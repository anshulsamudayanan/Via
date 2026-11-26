"""What a check sees: the design plus indexes built once per analysis run."""

from __future__ import annotations

from dataclasses import dataclass, field
from functools import cached_property
from typing import Any

from via_pcb.models import Component, Pad, PCBDesign


@dataclass
class AnalysisContext:
    design: PCBDesign
    #: Per-run options (e.g. a manufacturing profile). Checks read only keys they own.
    options: dict[str, Any] = field(default_factory=dict)
    #: Facts a check wants recorded with its run (e.g. tool version), keyed by check id.
    notes: dict[str, dict[str, Any]] = field(default_factory=dict)

    @cached_property
    def components_by_id(self) -> dict[str, Component]:
        return {c.id: c for c in self.design.components if c.id}

    @cached_property
    def by_uuid(self) -> dict[str, tuple[str, str, str]]:
        """Source UUID -> (object kind, stable id, label) for components, pads, tracks, vias and zones."""
        out: dict[str, tuple[str, str, str]] = {}
        for c in self.design.components:
            if c.uuid and c.id:
                out.setdefault(c.uuid, ("component", c.id, c.reference or c.footprint))
            for p in c.pads:
                if p.uuid and p.id:
                    out.setdefault(p.uuid, ("pad", p.id, f"{c.reference} pad {p.number}"))
        for t in self.design.tracks:
            if t.uuid and t.id:
                kind = "Arc track" if t.kind == "arc" else "Track"
                net = f" [{t.net}]" if t.net else ""
                out.setdefault(t.uuid, ("track", t.id, f"{kind} on {t.layer}{net}, {t.length:.2f} mm"))
        for v in self.design.vias:
            if v.uuid and v.id:
                out.setdefault(v.uuid, ("via", v.id, "Via" + (f" [{v.net}]" if v.net else "")))
        for z in self.design.zones:
            if z.uuid and z.id:
                out.setdefault(z.uuid, ("zone", z.id, z.name or ("Keep-out" if z.keepout else f"Zone [{z.net or ''}]")))
        return out

    @cached_property
    def pad_by_ref(self) -> dict[tuple[str, str], tuple[str, str]]:
        """(reference, pad number) -> (pad id, label), first pad wins."""
        out: dict[tuple[str, str], tuple[str, str]] = {}
        for c in self.design.components:
            for p in c.pads:
                if p.id:
                    out.setdefault((c.reference, p.number), (p.id, f"{c.reference} pad {p.number}"))
        return out

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
