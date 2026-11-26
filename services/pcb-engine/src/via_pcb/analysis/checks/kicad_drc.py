"""KiCad's own design rule checker, reported as KiCad's findings.

The worker runs ``kicad-cli pcb drc`` (KiCad 9, via the internal eda-runner service) on the
uploaded board with the project's rule files, and passes the JSON report in
``options["kicad_drc"]``. This check only translates: KiCad decides what is a violation. Each
violation's items are mapped to VIA objects by UUID (or, when KiCad generated the UUID at load
time, by "Pad N of REF" / "Footprint REF" in its description); unmapped items keep their
description and position as evidence.

Without the project's .kicad_pro, KiCad uses its default rules, so results are marked
``heuristic`` with reduced confidence and say so.
"""

from __future__ import annotations

import re
from collections.abc import Iterable
from typing import Any

from via_pcb.analysis.context import AnalysisContext
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
from via_pcb.analysis.registry import Check
from via_pcb.models import BoundingBox, Point

#: Violations about the server's environment, not the design (footprint libraries aren't installed).
SUPPRESSED = {"lib_footprint_issues", "lib_footprint_mismatch", "footprint_filters_mismatch"}

_CRITICAL = {"shorting_items", "tracks_crossing"}
_LOW = {
    "silk_over_copper", "silk_edge_clearance", "silk_overlap", "text_height", "text_thickness",
    "mirrored_text_on_front_layer", "nonmirrored_text_on_back_layer", "missing_courtyard",
    "malformed_courtyard", "footprint_type_mismatch", "invalid_field", "unresolved_variable",
}  # fmt: skip
_CATEGORY = {
    **{t: Category.CONNECTIVITY for t in ("unconnected_items", "isolated_copper", "track_dangling", "via_dangling",
                                          "starved_thermal", "connection_width")},
    **{t: Category.PLACEMENT for t in ("courtyards_overlap", "missing_courtyard", "malformed_courtyard",
                                       "npth_inside_courtyard", "pth_inside_courtyard")},
    **{t: Category.MANUFACTURING for t in ("silk_over_copper", "silk_edge_clearance", "silk_overlap", "text_height",
                                           "text_thickness", "solder_mask_bridge", "copper_sliver",
                                           "copper_edge_clearance", "hole_to_hole", "annular_width",
                                           "drill_out_of_range", "via_diameter", "microvia_drill_out_of_range",
                                           "holes_co_located")},
    "invalid_outline": Category.BOARD_OUTLINE,
}  # fmt: skip
_TITLES = {
    "unconnected_items": "Unconnected items",
    "shorting_items": "Items short two nets",
    "tracks_crossing": "Tracks cross",
    "clearance": "Clearance violation",
    "hole_clearance": "Hole clearance violation",
    "copper_edge_clearance": "Copper too close to the board edge",
    "track_width": "Track width out of range",
    "annular_width": "Annular ring too small",
    "drill_out_of_range": "Drill size out of range",
    "via_diameter": "Via diameter out of range",
    "hole_to_hole": "Holes too close together",
    "starved_thermal": "Thermal relief has too few spokes",
    "solder_mask_bridge": "Solder mask bridge between nets",
    "courtyards_overlap": "Courtyards overlap",
    "silk_over_copper": "Silkscreen over copper",
    "silk_edge_clearance": "Silkscreen too close to the board edge",
    "silk_overlap": "Silkscreen overlaps",
    "isolated_copper": "Isolated copper fill",
    "track_dangling": "Track has an unconnected end",
    "via_dangling": "Via isn't connected",
    "invalid_outline": "Board outline is invalid",
    "items_not_allowed": "Item in a keep-out area",
    "copper_sliver": "Copper sliver",
    "zones_intersect": "Zones intersect",
}
_EXPLANATIONS = {
    "unconnected_items": (
        "These items share a net but aren't connected by copper: the board won't work as drawn until they're routed."
    ),
    "shorting_items": "Copper of two different nets touches, which shorts them electrically.",
    "tracks_crossing": "Tracks of different nets cross on the same layer, which shorts them.",
    "clearance": (
        "Copper of different nets is closer than the rules allow, risking shorts in fabrication or arcing at voltage."
    ),
    "hole_clearance": "A hole is closer to copper than the rules allow; drill tolerance can then damage or short it.",
    "copper_edge_clearance": "Copper close to the edge can be exposed or cut during routing or V-scoring.",
    "annular_width": "Too little copper around a hole; drill wander can break the connection.",
    "hole_to_hole": "Holes too close together can break through into each other during drilling.",
    "solder_mask_bridge": "There's no solder mask between pads of different nets, so solder can bridge them.",
    "courtyards_overlap": "Component keep-out areas overlap, so the parts may collide during assembly.",
    "starved_thermal": "A thermal connection to a zone has fewer spokes than required, weakening the connection.",
}

_PAD_RE = re.compile(r"^Pad (\S+)\b.*? of (\S+)")
_FOOTPRINT_RE = re.compile(r"^Footprint (\S+)")
_NET_RE = re.compile(r"\[([^\]]+)\]")


def severity_for(kind: str, kicad_severity: str) -> Severity:
    if kind in _CRITICAL:
        return Severity.CRITICAL
    if kind in _LOW:
        return Severity.LOW
    return Severity.HIGH if kicad_severity == "error" else Severity.MEDIUM


class KiCadDrcCheck(Check):
    id = "kicad_drc"
    version = "1.0.0"
    category = Category.DESIGN_RULES
    title = "KiCad design rule check"
    description = "KiCad's own DRC (kicad-cli) on the uploaded board with the project's rules."
    source = Source.KICAD_DRC

    def skip_reason(self, ctx: AnalysisContext) -> str | None:
        data = ctx.options.get("kicad_drc")
        if not isinstance(data, dict):
            return "KiCad DRC wasn't run for this analysis."
        if data.get("error"):
            return f"KiCad DRC couldn't run: {data['error']}"
        if not isinstance(data.get("report"), dict):
            return "KiCad DRC returned no report."
        return None

    def run(self, ctx: AnalysisContext) -> Iterable[Finding]:
        data: dict[str, Any] = ctx.options["kicad_drc"]
        report: dict[str, Any] = data["report"]
        version = ctx.kicad_file_version
        project_rules = data.get("rules") == "project_file" or (version is not None and version <= 20171130)
        rules_label = (
            "project rules (.kicad_pro)"
            if data.get("rules") == "project_file"
            else (
                "rules stored in the board file (KiCad 5)" if project_rules else "KiCad default rules (no .kicad_pro)"
            )
        )
        refs = {c.reference: c for c in ctx.design.components if c.reference}
        violations = [*report.get("violations", []), *report.get("unconnected_items", [])]
        suppressed = 0
        produced: list[Finding] = []
        for v in violations:
            kind = str(v.get("type", "unknown"))
            if kind in SUPPRESSED:
                suppressed += 1
                continue
            produced.append(self._finding(ctx, v, kind, project_rules, rules_label, data, refs))
        ctx.notes[self.id] = {
            "kicad_version": data.get("kicad_version"),
            "rules": rules_label,
            "kicad_violations": len(violations),
            "suppressed_environment_checks": suppressed,
            "suppressed_types": sorted(SUPPRESSED),
            "zones": "checked as filled in the file (not refilled)",
            "duration_seconds": data.get("duration_seconds"),
        }
        return produced

    def _finding(self, ctx, v, kind, project_rules, rules_label, data, refs) -> Finding:
        kicad_severity = str(v.get("severity", "error"))
        objects: list[ObjectRef] = []
        keys: list[str] = []
        components: set[str] = set()
        nets: set[str] = set()
        points: list[Point] = []
        evidence = [
            Evidence(kind="tool_output", label="KiCad", value=str(v.get("description", kind))),
            Evidence(kind="tool_output", label="KiCad severity", value=kicad_severity),
            Evidence(kind="rule", label="Rules", value=rules_label),
        ]
        for item in v.get("items", []):
            desc = str(item.get("description", ""))
            pos = item.get("pos") or {}
            point = Point(x=float(pos.get("x", 0.0)), y=float(pos.get("y", 0.0))) if pos else None
            if point is not None:
                points.append(point)
            ref = self._map(ctx, str(item.get("uuid", "")), desc, refs)
            if ref is not None:
                objects.append(ref)
                keys.append(f"{ref.kind}:{ref.id}")
                if ref.kind in (ObjectKind.COMPONENT, ObjectKind.PAD) and ref.label:
                    components.add(ref.label.split(" pad ")[0])
            else:
                keys.append(f"{desc}@{point.x:.2f},{point.y:.2f}" if point else desc)
            nets.update(n for n in _NET_RE.findall(desc) if n != "<no net>")
            where = f" at ({point.x:g}, {point.y:g}) mm" if point else ""
            evidence.append(Evidence(kind="tool_output", label="Item", value=f"{desc}{where}"))
        region = None
        if points:
            region = Region(
                bbox=BoundingBox(
                    min_x=min(p.x for p in points), min_y=min(p.y for p in points),
                    max_x=max(p.x for p in points), max_y=max(p.y for p in points),
                ),
                points=points,
            )  # fmt: skip
        title = _TITLES.get(kind, kind.replace("_", " ").capitalize())
        explanation = _EXPLANATIONS.get(kind, "Reported by KiCad's design rule checker under the rules shown.")
        if not project_rules:
            explanation += (
                " This board was checked with KiCad's default rules because its project file wasn't uploaded, "
                "so this may not reflect the designer's actual rules."
            )
        return Finding(
            check_id=self.id,
            rule=kind,
            category=_CATEGORY.get(kind, Category.DESIGN_RULES),
            severity=severity_for(kind, kicad_severity),
            title=title,
            description=str(v.get("description", title)),
            explanation=explanation,
            objects=objects,
            components=sorted(components),
            nets=sorted(nets),
            region=region,
            source=Source.KICAD_DRC,
            verification=Verification.VERIFIED if project_rules else Verification.HEURISTIC,
            confidence=1.0 if project_rules else 0.6,
            evidence=evidence,
            suggested_resolution="Fix in KiCad and re-run DRC there, then upload the new revision.",
        ).with_fingerprint(kind, *sorted(keys))

    @staticmethod
    def _map(ctx: AnalysisContext, uuid: str, desc: str, refs) -> ObjectRef | None:
        hit = ctx.by_uuid.get(uuid) if uuid else None
        if hit is not None:
            kind, oid, label = hit
            return ObjectRef(kind=ObjectKind(kind), id=oid, label=label)
        m = _PAD_RE.match(desc)
        if m and (pad := ctx.pad_by_ref.get((m.group(2), m.group(1)))):
            return ObjectRef(kind=ObjectKind.PAD, id=pad[0], label=pad[1])
        m = _FOOTPRINT_RE.match(desc)
        if m and (comp := refs.get(m.group(1))) and comp.id:
            return ObjectRef(kind=ObjectKind.COMPONENT, id=comp.id, label=comp.reference)
        return None
