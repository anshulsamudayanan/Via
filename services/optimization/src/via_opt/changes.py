"""Explicit design changes: the only way VIA Optimize (and later VIA Studio) proposes edits.

A change names its target by stable id (and source UUID when known), records the value before and
after, why, and where it came from. ``apply`` produces a *new* design; the original is never mutated.
``via_opt.export`` writes supported changes into the original file (see docs/CHANGE_MANAGEMENT.md).
"""

from __future__ import annotations

from enum import StrEnum
from typing import Any

from pydantic import BaseModel, ConfigDict, Field

from via_pcb import geometry as geo
from via_pcb.models import BoundingBox, Graphic, PCBDesign, Point


class ChangeKind(StrEnum):
    MOVE_COMPONENT = "move_component"  # after: {x, y}
    ROTATE_COMPONENT = "rotate_component"  # after: {rotation}
    SET_TRACK_WIDTH = "set_track_width"  # after: {width}
    MOVE_VIA = "move_via"  # after: {x, y}
    SET_VIA_SIZE = "set_via_size"  # after: {diameter, drill}
    SET_OUTLINE_RECT = "set_outline_rect"  # after: {min_x, min_y, max_x, max_y}
    SET_COPPER_LAYER_COUNT = "set_copper_layer_count"  # after: {count}; not applicable automatically


#: Kinds ``via_pcb.patch`` can write back into a KiCad file. Others need manual work in the EDA tool.
EXPORTABLE = {
    ChangeKind.MOVE_COMPONENT, ChangeKind.ROTATE_COMPONENT, ChangeKind.SET_TRACK_WIDTH, ChangeKind.MOVE_VIA,
    ChangeKind.SET_VIA_SIZE, ChangeKind.SET_OUTLINE_RECT,
}  # fmt: skip


class Target(BaseModel):
    model_config = ConfigDict(extra="forbid")

    kind: str = Field(description="component | track | via | outline | stackup")
    id: str
    uuid: str | None = None
    label: str | None = None


class Change(BaseModel):
    model_config = ConfigDict(extra="forbid")

    kind: ChangeKind
    target: Target
    before: dict[str, Any]
    after: dict[str, Any]
    reason: str
    source: str = Field(default="via_optimize", description="via_optimize | user | ai_suggestion")
    finding_ids: list[str] = Field(default_factory=list)

    @property
    def exportable(self) -> bool:
        return self.kind in EXPORTABLE


class UnsupportedChange(ValueError):
    """The change can't be applied to the normalized model automatically."""


def apply(design: PCBDesign, changes: list[Change]) -> PCBDesign:
    """A copy of ``design`` with ``changes`` applied (moves carry pads and graphics along)."""
    out = design.model_copy(deep=True)
    comps = {c.id: c for c in out.components if c.id}
    tracks = {t.id: t for t in out.tracks if t.id}
    vias = {v.id: v for v in out.vias if v.id}
    for ch in changes:
        a = ch.after
        if ch.kind == ChangeKind.MOVE_COMPONENT:
            c = comps[ch.target.id]
            dx, dy = float(a["x"]) - c.position.x, float(a["y"]) - c.position.y
            c.position = Point(x=float(a["x"]), y=float(a["y"]))
            for p in c.pads:
                p.position = Point(x=p.position.x + dx, y=p.position.y + dy)
            for g in c.graphics:
                g.points = [Point(x=q.x + dx, y=q.y + dy) for q in g.points]
        elif ch.kind == ChangeKind.ROTATE_COMPONENT:
            c = comps[ch.target.id]
            delta = float(a["rotation"]) - c.rotation
            origin = (c.position.x, c.position.y)

            def turn(q: Point, o: tuple[float, float] = origin, d: float = delta) -> Point:
                x, y = geo.to_board((q.x - o[0], q.y - o[1]), o, d)
                return Point(x=x, y=y)

            c.rotation = float(a["rotation"]) % 360
            for p in c.pads:
                p.position = turn(p.position)
                p.rotation = (p.rotation + delta) % 360
            for g in c.graphics:
                g.points = [turn(q) for q in g.points]
        elif ch.kind == ChangeKind.SET_TRACK_WIDTH:
            tracks[ch.target.id].width = float(a["width"])
        elif ch.kind == ChangeKind.MOVE_VIA:
            vias[ch.target.id].position = Point(x=float(a["x"]), y=float(a["y"]))
        elif ch.kind == ChangeKind.SET_VIA_SIZE:
            v = vias[ch.target.id]
            v.diameter, v.drill = float(a["diameter"]), float(a["drill"])
        elif ch.kind == ChangeKind.SET_OUTLINE_RECT:
            x1, y1, x2, y2 = (float(a[k]) for k in ("min_x", "min_y", "max_x", "max_y"))
            g = Graphic(kind="rect", layer="Edge.Cuts", width=0.05, points=[Point(x=x1, y=y1), Point(x=x2, y=y2)])
            out.outline.graphics = [g]
            out.outline.closed = True
            out.outline.bbox = BoundingBox(min_x=x1, min_y=y1, max_x=x2, max_y=y2)
            out.outline.area = round((x2 - x1) * (y2 - y1), 6)
            out.stats.board_width, out.stats.board_height = round(x2 - x1, 6), round(y2 - y1, 6)
            out.stats.board_area = out.outline.area
        else:
            raise UnsupportedChange(f"{ch.kind} can't be applied automatically")
    return out
