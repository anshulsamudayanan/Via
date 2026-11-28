# ruff: noqa: E501  (KiCad S-expression templates)
"""Tiny KiCad 8 board builder for analysis tests (original work; values chosen by hand).

Only what the parser needs is written. Coordinates in mm. Footprints are placed at ``(x, y)`` with
pads relative to that origin.
"""

from __future__ import annotations

import itertools
from dataclasses import dataclass, field

_uuid = itertools.count(1)


def uid() -> str:
    return f"00000000-0000-4000-8000-{next(_uuid):012d}"


@dataclass
class Board:
    copper: tuple[str, ...] = ("F.Cu", "B.Cu")
    outline: tuple[float, float, float, float] | None = (0, 0, 40, 30)
    nets: list[str] = field(default_factory=list)
    items: list[str] = field(default_factory=list)

    def net(self, name: str | None) -> str:
        if not name:
            return ""
        if name not in self.nets:
            self.nets.append(name)
        return f'(net {self.nets.index(name) + 1} "{name}")'

    def footprint(self, ref: str, x: float, y: float, pads: list[dict], *, silk_width: float | None = None,
                  rotation: float = 0, lib: str = "Lib:Part", props: dict[str, str] | None = None) -> Board:  # fmt: skip
        body = [f'(footprint "{lib}" (layer "F.Cu") (uuid "{uid()}") (at {x} {y} {rotation})',
                f'  (property "Reference" "{ref}" (at 0 0 0) (layer "F.SilkS"))']  # fmt: skip
        for key, val in (props or {}).items():
            body.append(f'  (property "{key}" "{val}" (at 0 0 0) (layer "F.Fab") (hide yes))')
        for p in pads:
            kind = p.get("type", "smd")
            layers = p.get("layers") or ('"*.Cu"' if kind in ("thru_hole", "np_thru_hole") else '"F.Cu"')
            drill = f" (drill {p['drill']})" if "drill" in p else ""
            rr = f" (roundrect_rratio {p['rr']})" if "rr" in p else ""
            size = p.get("size", (1, 1))
            px, py = p.get("at", (0, 0))
            body.append(
                f'  (pad "{p.get("num", "1")}" {kind} {p.get("shape", "rect")} (at {px} {py} {p.get("angle", rotation)}) '
                f'(size {size[0]} {size[1]}){drill} (layers {layers}){rr} {self.net(p.get("net"))} (uuid "{uid()}"))'
            )
        if silk_width is not None:
            body.append(
                f'  (fp_line (start -1 -1) (end 1 -1) (stroke (width {silk_width}) (type solid)) (layer "F.SilkS"))'
            )
        body.append(")")
        self.items.append("\n".join(body))
        return self

    def track(self, a: tuple[float, float], b: tuple[float, float], width: float, net: str | None,
              layer: str = "F.Cu") -> Board:  # fmt: skip
        self.items.append(
            f'(segment (start {a[0]} {a[1]}) (end {b[0]} {b[1]}) (width {width}) (layer "{layer}") {self.net(net)} (uuid "{uid()}"))'
        )
        return self

    def via(self, at: tuple[float, float], size: float, drill: float, net: str | None) -> Board:
        self.items.append(
            f'(via (at {at[0]} {at[1]}) (size {size}) (drill {drill}) (layers "F.Cu" "B.Cu") {self.net(net)} (uuid "{uid()}"))'
        )
        return self

    def zone(self, net: str, layer: str, pts: list[tuple[float, float]]) -> Board:
        xy = " ".join(f"(xy {x} {y})" for x, y in pts)
        self.items.append(
            f'(zone {self.net(net)} (net_name "{net}") (layer "{layer}") (uuid "{uid()}") (polygon (pts {xy})))'
        )
        return self

    def text(self) -> str:
        # Placeholders first so net numbers are known; then the net table.
        body = "\n".join(self.items)
        layer_ids = {"F.Cu": 0, "B.Cu": 2, "In1.Cu": 4, "In2.Cu": 6}
        layers = "\n".join(f'    ({layer_ids[c]} "{c}" signal)' for c in self.copper)
        nets = "\n".join(f'  (net {i + 1} "{n}")' for i, n in enumerate(self.nets))
        outline = ""
        if self.outline:
            x1, y1, x2, y2 = self.outline
            outline = (f'(gr_rect (start {x1} {y1}) (end {x2} {y2}) (stroke (width 0.05) (type default)) '
                       f'(fill no) (layer "Edge.Cuts") (uuid "{uid()}"))')  # fmt: skip
        return f"""(kicad_pcb (version 20240108) (generator "pcbnew") (generator_version "8.0")
  (general (thickness 1.6))
  (layers
{layers}
    (25 "Edge.Cuts" user)
    (5 "F.SilkS" user)
  )
  (setup (pad_to_mask_clearance 0))
  (net 0 "")
{nets}
{body}
{outline}
)
"""

    def bytes(self) -> bytes:
        return self.text().encode()
