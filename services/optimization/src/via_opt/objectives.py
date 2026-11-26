"""Objectives and the metrics that measure them. Every metric is minimized.

Metrics are computed from the design itself (deterministic). ``cost_index`` is VIA's illustrative
relative cost model (documented in docs/OPTIMIZATION_ENGINE.md), an estimate and never a quote.
"""

from __future__ import annotations

from collections import defaultdict
from enum import StrEnum
from typing import Any

from via_pcb.analysis import default_engine
from via_pcb.analysis.checks.manufacturing import MANUFACTURING_CHECKS
from via_pcb.analysis.checks.routing import mst_length
from via_pcb.analysis.profiles import BUILTIN
from via_pcb.models import PCBDesign


class Objective(StrEnum):
    AREA = "area"
    PLACEMENT = "placement"
    ROUTING = "routing"
    COST = "cost"
    LAYERS = "layers"
    THERMAL = "thermal"
    MANUFACTURABILITY = "manufacturability"


#: The metric each objective minimizes.
METRIC_FOR = {
    Objective.AREA: "board_area_mm2",
    Objective.PLACEMENT: "ratsnest_mm",
    Objective.ROUTING: "routed_length_mm",
    Objective.COST: "cost_index",
    Objective.LAYERS: "copper_layers_used",
    Objective.THERMAL: "current_capacity_issues",
    Objective.MANUFACTURABILITY: "manufacturing_issues",
}

#: Relative cost per copper-layer count (illustrative; real prices vary by fabricator and volume).
LAYER_FACTOR = {1: 0.8, 2: 1.0, 4: 1.9, 6: 2.8, 8: 3.8}

_MFG_IDS = {c.id for c in MANUFACTURING_CHECKS}


def ratsnest(design: PCBDesign) -> float:
    """Sum over nets of the minimum spanning tree of pad positions (shorter = better placement)."""
    pads: dict[str, set[tuple[float, float]]] = defaultdict(set)
    for c in design.components:
        for p in c.pads:
            if p.net:
                pads[p.net].add((round(p.position.x, 4), round(p.position.y, 4)))
    return sum(mst_length(sorted(pts)) for pts in pads.values() if len(pts) > 1)


def fab_class_factor(design: PCBDesign) -> float:
    """1.0 if the smallest features fit VIA conservative, 1.3 if they need VIA advanced, else 1.6."""
    widths = [t.width for t in design.tracks if t.width > 0]
    drills = [v.drill for v in design.vias if v.drill > 0]
    w, d = min(widths, default=1.0), min(drills, default=1.0)
    cons, adv = BUILTIN["via-conservative"], BUILTIN["via-advanced"]
    if w >= cons.min_track_width - 1e-6 and d >= cons.min_drill - 1e-6:
        return 1.0
    if w >= adv.min_track_width - 1e-6 and d >= adv.min_drill - 1e-6:
        return 1.3
    return 1.6


def copper_layers_used(design: PCBDesign) -> int:
    used = {t.layer for t in design.tracks} | {layer for z in design.zones if not z.keepout for layer in z.layers}
    used |= {
        layer for c in design.components for p in c.pads if p.type.value in ("smd", "connect") for layer in p.layers
    }
    copper = {layer.name for layer in design.layers if layer.kind == "copper"}
    return len(used & copper) or len(copper)


def metrics(design: PCBDesign, options: dict[str, Any] | None = None) -> dict[str, float | None]:
    options = options or {}
    bbox = design.outline.bbox or design.bbox
    area = design.outline.area if design.outline.area else (bbox.width * bbox.height if bbox else None)
    copper = design.stats.copper_layer_count
    result = default_engine().run(design, options=options, only=_MFG_IDS | {"track_current_capacity"})
    mfg = sum(1 for f in result.findings if f.check_id in _MFG_IDS and f.severity.rank <= 2)
    current_ran = any(c.check_id == "track_current_capacity" and c.status.value == "ok" for c in result.checks)
    current = sum(1 for f in result.findings if f.check_id == "track_current_capacity") if current_ran else None
    cost = (area / 100.0) * LAYER_FACTOR.get(copper, 1.0 + 0.45 * copper) * fab_class_factor(design) if area else None
    return {
        "board_area_mm2": round(area, 3) if area else None,
        "ratsnest_mm": round(ratsnest(design), 3),
        "routed_length_mm": round(sum(t.length for t in design.tracks), 3),
        "via_count": len(design.vias),
        "copper_layers_used": copper_layers_used(design),
        "copper_layer_count": copper,
        "manufacturing_issues": mfg,
        "current_capacity_issues": current,
        "cost_index": round(cost, 3) if cost is not None else None,
    }
