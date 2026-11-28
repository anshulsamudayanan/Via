"""Measurements that aren't candidates: where the board's space goes and how close it runs to the profile.

Everything here is computed from the design (deterministic); nothing is estimated from a model of the fabricator.
"""

from __future__ import annotations

import math
from typing import Any

from via_opt.algorithms.outline import content_box, is_rectangular
from via_pcb.analysis import default_engine
from via_pcb.analysis.checks.manufacturing import MANUFACTURING_CHECKS
from via_pcb.analysis.checks.placement import extent
from via_pcb.analysis.profiles import ManufacturingProfile
from via_pcb.models import BoundingBox, PCBDesign

VERSION = "1.0.0"
MAX_CELLS = 40_000
#: Margin beyond this many mm of unused space between the content and the outline is reported.
SLACK_REPORT_MM = 5.0
#: Manufacturing rule margin: a feature within this fraction above a profile minimum is a potential risk.
RISK_FRACTION = 0.25

#: Profile limits each manufacturing check enforces.
CHECK_LIMITS = {
    "mfg_track_width": ["min_track_width"],
    "mfg_vias": ["min_via_diameter", "min_drill", "min_annular_ring"],
    "mfg_pad_holes": ["min_drill"],
    "mfg_hole_spacing": ["min_hole_to_hole"],
    "mfg_copper_to_edge": ["min_copper_to_edge"],
    "mfg_copper_spacing": ["min_clearance"],
    "mfg_silkscreen": ["min_silk_width"],
}


def _cells(ob: BoundingBox) -> tuple[float, int, int]:
    size = max(0.1, math.sqrt(max(ob.width * ob.height, 1e-9) / MAX_CELLS))
    return size, max(1, math.ceil(ob.width / size)), max(1, math.ceil(ob.height / size))


def _fill(
    grid: list[bytearray], ob: BoundingBox, size: float, box: tuple[float, float, float, float], inclusive: bool = True
) -> None:
    """Marks the cells a box covers: every cell it touches (``inclusive``, errs towards less empty space) or the
    cells whose centre it contains (closest to its true area)."""
    rows, cols = len(grid), len(grid[0])
    if inclusive:
        x0, x1 = int((box[0] - ob.min_x) // size), int((box[2] - ob.min_x) // size)
        y0, y1 = int((box[1] - ob.min_y) // size), int((box[3] - ob.min_y) // size)
    else:
        x0, x1 = math.ceil((box[0] - ob.min_x) / size - 0.5), math.floor((box[2] - ob.min_x) / size - 0.5)
        y0, y1 = math.ceil((box[1] - ob.min_y) / size - 0.5), math.floor((box[3] - ob.min_y) / size - 0.5)
    for r in range(max(0, y0), min(rows - 1, y1) + 1):
        row = grid[r]
        for c in range(max(0, x0), min(cols - 1, x1) + 1):
            row[c] = 1


def _largest_empty_rectangle(grid: list[bytearray]) -> tuple[int, int, int, int]:
    """(area in cells, width, row, col of the top-left cell) of the largest all-empty rectangle (histogram method)."""
    cols = len(grid[0])
    heights = [0] * cols
    best = (0, 0, 0, 0)
    for r, row in enumerate(grid):
        for c in range(cols):
            heights[c] = heights[c] + 1 if not row[c] else 0
        stack: list[int] = []
        for c in range(cols + 1):
            h = heights[c] if c < cols else 0
            while stack and heights[stack[-1]] >= h:
                top = heights[stack.pop()]
                left = stack[-1] + 1 if stack else 0
                area = top * (c - left)
                if area > best[0]:
                    best = (area, c - left, r - top + 1, left)
            stack.append(c)
    return best


def area_analysis(design: PCBDesign) -> dict[str, Any]:
    """Board dimensions, how much of the board the parts occupy, unused margins and the largest empty region."""
    ob = design.outline.bbox
    out: dict[str, Any] = {"version": VERSION, "observations": []}
    if ob is None or ob.width <= 0 or ob.height <= 0:
        out["available"] = False
        out["observations"].append("The design has no usable board outline, so area can't be analysed.")
        return out
    rectangular = is_rectangular(design)
    area = design.outline.area or ob.width * ob.height
    boxes = [e for c in design.components if (e := extent(c)) is not None]
    size, cols, rows = _cells(ob)
    parts = [bytearray(cols) for _ in range(rows)]
    touched = [bytearray(cols) for _ in range(rows)]
    for e in boxes:
        _fill(parts, ob, size, (e.min_x, e.min_y, e.max_x, e.max_y), inclusive=False)
        _fill(touched, ob, size, (e.min_x, e.min_y, e.max_x, e.max_y))
    occupied_cells = sum(sum(r) for r in parts)
    occupied = min(occupied_cells * size * size, area)
    out.update(
        available=True,
        board_width_mm=round(ob.width, 3),
        board_height_mm=round(ob.height, 3),
        outline_area_mm2=round(area, 3),
        rectangular=rectangular,
        component_count=len(design.components),
        occupied_area_mm2=round(occupied, 3),
        utilisation=round(occupied / area, 4) if area else None,
        resolution_mm=round(size, 3),
    )
    box = content_box(design)
    if box is not None:
        slack = {
            "left": box[0] - ob.min_x,
            "top": box[1] - ob.min_y,
            "right": ob.max_x - box[2],
            "bottom": ob.max_y - box[3],
        }
        out["unused_margin_mm"] = {k: round(max(v, 0.0), 3) for k, v in slack.items()}
        for side, v in slack.items():
            if v > SLACK_REPORT_MM:
                out["observations"].append(
                    f"{v:.1f} mm of the {side} side of the outline holds no parts, tracks, vias or zones."
                )
    # Empty = no part, track or via (diagonal tracks are boxed, so this errs towards less empty space).
    busy = [bytearray(r) for r in touched]
    for t in design.tracks:
        hw = t.width / 2
        _fill(busy, ob, size, (min(t.start.x, t.end.x) - hw, min(t.start.y, t.end.y) - hw,
                               max(t.start.x, t.end.x) + hw, max(t.start.y, t.end.y) + hw))  # fmt: skip
    for via in design.vias:
        rad = via.diameter / 2
        _fill(busy, ob, size, (via.position.x - rad, via.position.y - rad, via.position.x + rad, via.position.y + rad))
    if rectangular:
        cells, w, r0, c0 = _largest_empty_rectangle(busy)
        x, y = ob.min_x + c0 * size, ob.min_y + r0 * size
        width = min(w * size, ob.max_x - x)  # the grid can overhang the outline by under one cell
        height = min((cells / w * size) if w else 0.0, ob.max_y - y)
        out["largest_empty_rectangle"] = {
            "area_mm2": round(width * height, 3),
            "width_mm": round(width, 3),
            "height_mm": round(height, 3),
            "x_mm": round(x, 3),
            "y_mm": round(y, 3),
        }
    else:
        out["largest_empty_rectangle"] = None
        out["observations"].append("The outline isn't rectangular, so the largest empty rectangle isn't computed.")
    # A coarse density map for the UI: fraction of each block covered by parts.
    n = 6
    density = []
    for br in range(n):
        row_out = []
        for bc in range(n):
            r0, r1 = br * rows // n, max((br + 1) * rows // n, br * rows // n + 1)
            c0, c1 = bc * cols // n, max((bc + 1) * cols // n, bc * cols // n + 1)
            block = [parts[r][c] for r in range(r0, min(r1, rows)) for c in range(c0, min(c1, cols))]
            row_out.append(round(sum(block) / len(block), 3) if block else 0.0)
        density.append(row_out)
    out["density_grid"] = density
    return out


def _stricter(profile: ManufacturingProfile, fraction: float) -> dict[str, Any]:
    values = profile.model_dump()
    for k in values:
        if k.startswith("min_"):
            values[k] = round(values[k] * (1 + fraction), 6)
    return values


def margin_analysis(design: PCBDesign, options: dict[str, Any], profile: ManufacturingProfile) -> dict[str, Any]:
    """Per manufacturing rule: features that break the profile (verified violations) and features that pass but
    sit within RISK_FRACTION of its limit (potential risks, a VIA heuristic and not a fabricator's statement)."""
    ids = {c.id for c in MANUFACTURING_CHECKS}
    engine = default_engine()
    base = engine.run(design, options=options, only=ids)
    tight = engine.run(
        design, options={**options, "manufacturing_profile": _stricter(profile, RISK_FRACTION)}, only=ids
    )
    skipped = {c.check_id: c.message or "skipped" for c in base.checks if c.status.value != "ok"}
    # Findings are grouped (e.g. per net), so features are compared, not findings: a net that already violates
    # must not hide its other, merely close, features.
    rules = []
    for check in MANUFACTURING_CHECKS:
        if check.id in skipped:
            rules.append({"check": check.id, "title": check.title, "ran": False, "reason": skipped[check.id]})
            continue
        v = [f for f in base.findings if f.check_id == check.id]
        t = [f for f in tight.findings if f.check_id == check.id]
        bad = {(o.kind, o.id) for f in v for o in f.objects}
        risky = {(o.kind, o.id) for f in t for o in f.objects} - bad
        r = [f for f in t if any((o.kind, o.id) in risky for o in f.objects)]
        limits = {k: getattr(profile, k) for k in CHECK_LIMITS.get(check.id, [])}
        rules.append({
            "check": check.id, "title": check.title, "ran": True, "limits": limits,
            "violations": len(v), "violating_features": len(bad), "potential_risk_features": len(risky),
            "risk_threshold": {k: round(x * (1 + RISK_FRACTION), 6) for k, x in limits.items()},
            "examples": [f"{f.title}: {f.description}"[:200] for f in (v[:2] if v else r[:2])],
        })  # fmt: skip
    return {
        "version": VERSION,
        "profile": {"key": profile.key, "name": profile.name, "source": profile.source},
        "risk_fraction": RISK_FRACTION,
        "rules": rules,
        "violating_features": sum(x.get("violating_features", 0) for x in rules),
        "potential_risk_features": sum(x.get("potential_risk_features", 0) for x in rules),
        "notes": [
            "Violations are measured against the profile's own limits. Potential risks are features within "
            f"{RISK_FRACTION:.0%} above a limit: a VIA heuristic, not a fabricator's capability statement.",
            "VIA can't state that a design is manufacturable: that needs your fabricator's rules (a project profile).",
        ],
    }
