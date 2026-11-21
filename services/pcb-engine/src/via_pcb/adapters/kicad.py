"""KiCad ``.kicad_pcb`` adapter.

Supports the S-expression board format written by KiCad 5 through 9
(file versions ``20171130`` .. ``2025xxxx``). Older files are attempted with a
warning; anything that is not a ``kicad_pcb`` S-expression is rejected.

What is extracted (and only this — see docs/ENGINEERING.md):
layers, nets, footprints (reference, value, position, rotation, side,
attributes, properties, pads, graphics), tracks (segments + arcs), vias,
zones, board graphics, Edge.Cuts outline, board thickness, a few setup rules
and legacy in-file net classes.

Not extracted: text objects, dimensions, 3D models, groups, the ``.kicad_pro``
design rules, bezier curves (reported as warnings).
"""

from __future__ import annotations

import hashlib
import re
from collections import defaultdict
from collections.abc import Iterable

from via_pcb import geometry as geo
from via_pcb.adapters.base import PCBAdapter, UnsupportedFormatError
from via_pcb.models import (
    BoardOutline,
    BoundingBox,
    Component,
    DesignConstraints,
    DesignStats,
    Drill,
    Graphic,
    Layer,
    LayerKind,
    Net,
    NetClass,
    NetStat,
    Pad,
    PadType,
    ParseWarning,
    PCBDesign,
    Point,
    Side,
    SourceInfo,
    Track,
    Via,
    Zone,
)
from via_pcb.parser import SExpr, SExprParseError, parse_sexpr

MIN_TESTED_VERSION = 20171130  # KiCad 5.0
MAX_TESTED_VERSION = 20250324  # KiCad 9.0

_PAD_TYPES = {
    "smd": PadType.SMD,
    "thru_hole": PadType.THROUGH_HOLE,
    "np_thru_hole": PadType.NPTH,
    "connect": PadType.CONNECT,
}

# Nodes we knowingly skip without warning (no electrical/geometric meaning for Stage 1).
_IGNORED_TOP = {
    "version",
    "host",
    "generator",
    "generator_version",
    "general",
    "paper",
    "page",
    "title_block",
    "layers",
    "setup",
    "net",
    "net_class",
    "gr_text",
    "gr_text_box",
    "dimension",
    "group",
    "target",
    "embedded_fonts",
    "embedded_files",
    "image",
    "property",
    "generated",
    "table",
    "footprint",
    "module",
    "segment",
    "arc",
    "via",
    "zone",
    "gr_line",
    "gr_arc",
    "gr_circle",
    "gr_rect",
    "gr_poly",
    "gr_curve",
    "gr_bbox",
}

_NUM_RE = re.compile(r"^-?\d+$")


def _layer_kind(name: str) -> tuple[LayerKind, Side]:
    side = Side.NONE
    if name.startswith("F."):
        side = Side.TOP
    elif name.startswith("B."):
        side = Side.BOTTOM
    elif name.startswith("In") and name.endswith(".Cu"):
        side = Side.INNER
    suffix = name.split(".", 1)[1] if "." in name else name
    table = {
        "Cu": LayerKind.COPPER,
        "SilkS": LayerKind.SILKSCREEN,
        "Silkscreen": LayerKind.SILKSCREEN,
        "Mask": LayerKind.SOLDER_MASK,
        "Paste": LayerKind.SOLDER_PASTE,
        "Adhes": LayerKind.ADHESIVE,
        "Adhesive": LayerKind.ADHESIVE,
        "Fab": LayerKind.FABRICATION,
        "CrtYd": LayerKind.COURTYARD,
        "Courtyard": LayerKind.COURTYARD,
        "Cuts": LayerKind.EDGE,
    }
    if name == "Margin":
        return LayerKind.MARGIN, side
    if name in {"Dwgs.User", "Cmts.User", "Eco1.User", "Eco2.User"}:
        return LayerKind.DOCUMENTATION, side
    return table.get(suffix, LayerKind.USER), side


def _xy(node: SExpr | None) -> geo.Vec | None:
    if node is None:
        return None
    nums = []
    for a in node.atoms():
        try:
            nums.append(float(a))
        except ValueError:
            continue
        if len(nums) == 2:
            return (nums[0], nums[1])
    return None


def _pt(v: geo.Vec) -> Point:
    return Point(x=round(v[0], 6), y=round(v[1], 6))


def _stroke_width(node: SExpr) -> float:
    stroke = node.child("stroke")
    if stroke is not None:
        w = stroke.number("width")
        if w is not None:
            return w
    return node.number("width", default=0.0) or 0.0


def _is_filled(node: SExpr) -> bool:
    fill = node.atom("fill")
    return fill in {"solid", "yes", "true"}


class _Context:
    """Per-parse mutable state."""

    def __init__(self) -> None:
        self.net_by_code: dict[int, str] = {}
        self.layers: list[Layer] = []
        self.warnings: list[ParseWarning] = []
        self._warned: dict[str, int] = defaultdict(int)

    def warn(self, code: str, message: str) -> None:
        # Collapse repeated warnings so a broken file cannot produce megabytes of them.
        self._warned[code] += 1
        if self._warned[code] <= 5:
            self.warnings.append(ParseWarning(code=code, message=message))

    def finish_warnings(self) -> None:
        for code, count in self._warned.items():
            if count > 5:
                self.warnings.append(ParseWarning(code=code, message=f"{count - 5} more '{code}' warnings suppressed"))

    @property
    def copper_layers(self) -> list[str]:
        return [layer.name for layer in self.layers if layer.kind == LayerKind.COPPER]

    def resolve_net(self, node: SExpr) -> str | None:
        net = node.child("net")
        if net is None:
            name = node.atom("net_name")
            return name or None
        atoms = net.atoms()
        if not atoms:
            return None
        if len(atoms) >= 2:
            return atoms[1] or None
        token = atoms[0]
        if _NUM_RE.match(token):
            code = int(token)
            if code == 0:
                return None
            if code not in self.net_by_code:
                self.warn("unknown_net", f"Reference to undeclared net code {code}")
                return None
            return self.net_by_code[code]
        return token or None

    def expand_layers(self, names: Iterable[str]) -> list[str]:
        known = [layer.name for layer in self.layers]
        out: list[str] = []
        for name in names:
            if name == "*.Cu":
                out.extend(self.copper_layers)
            elif name.startswith("*."):
                suffix = name[1:]
                out.extend(n for n in known if n.endswith(suffix) and n[:2] in {"F.", "B."})
            elif name.startswith("F&B."):
                suffix = name[3:]
                out.extend([f"F{suffix}", f"B{suffix}"])
            else:
                out.append(name)
        return list(dict.fromkeys(out))  # de-duplicate, keep order


class KiCadAdapter(PCBAdapter):
    format_id = "kicad"
    display_name = "KiCad PCB"
    extensions = (".kicad_pcb",)

    def sniff(self, head: bytes) -> bool:
        text = head.lstrip(b"\xef\xbb\xbf").lstrip()
        return text.startswith(b"(kicad_pcb")

    # ------------------------------------------------------------------ parse
    def parse(self, data: bytes, filename: str | None = None) -> PCBDesign:
        if not self.sniff(data[:4096]):
            raise UnsupportedFormatError("Not a KiCad PCB file: expected the file to start with '(kicad_pcb'")
        try:
            text = data.decode("utf-8-sig")
        except UnicodeDecodeError as exc:
            raise UnsupportedFormatError(f"File is not valid UTF-8 text: {exc.reason} at byte {exc.start}") from exc
        try:
            root = parse_sexpr(text)
        except SExprParseError as exc:
            raise UnsupportedFormatError(f"Malformed KiCad file: {exc}") from exc
        if root.name != "kicad_pcb":
            raise UnsupportedFormatError("Not a KiCad PCB file: top-level node is not 'kicad_pcb'")

        ctx = _Context()
        source = self._source_info(root, data, filename, ctx)
        ctx.layers = self._layers(root, ctx)
        nets = self._nets(root, ctx)

        components = [self._component(n, ctx) for n in root.children() if n.name in {"footprint", "module"}]
        tracks = self._tracks(root, ctx)
        vias = [self._via(n, ctx) for n in root.children("via")]
        zones = [z for n in root.children("zone") if (z := self._zone(n, ctx)) is not None]

        board_graphics: list[Graphic] = []
        for node in root.children():
            if node.name and node.name.startswith("gr_"):
                g = self._graphic(node, ctx, origin=None)
                if g is not None:
                    board_graphics.append(g)
            elif node.name not in _IGNORED_TOP:
                ctx.warn("unsupported_object", f"Ignored unsupported top-level object '{node.name}'")

        outline_graphics = [g for g in board_graphics if g.layer == "Edge.Cuts"]
        outline_graphics += [g for c in components for g in c.graphics if g.layer == "Edge.Cuts"]
        other_graphics = [g for g in board_graphics if g.layer != "Edge.Cuts"]
        outline = self._outline(outline_graphics, ctx)

        constraints = self._constraints(root)
        bbox = outline.bbox or self._content_bbox(components, tracks, vias, other_graphics)
        stats, net_stats = self._stats(ctx, nets, components, tracks, vias, zones, outline, constraints)
        ctx.finish_warnings()

        title_block = root.child("title_block")
        return PCBDesign(
            source=source,
            title=(title_block.atom("title") or None) if title_block is not None else None,
            layers=ctx.layers,
            nets=nets,
            components=components,
            tracks=tracks,
            vias=vias,
            zones=zones,
            graphics=other_graphics,
            outline=outline,
            constraints=constraints,
            bbox=bbox,
            stats=stats,
            net_stats=net_stats,
            warnings=ctx.warnings,
        )

    # --------------------------------------------------------------- sections
    def _source_info(self, root: SExpr, data: bytes, filename: str | None, ctx: _Context) -> SourceInfo:
        version = root.atom("version")
        if version is None:
            ctx.warn("missing_version", "File has no (version ...) header")
        elif version.isdigit():
            v = int(version)
            if v < MIN_TESTED_VERSION:
                ctx.warn("old_version", f"File version {v} predates KiCad 5; results may be incomplete")
            elif v > MAX_TESTED_VERSION:
                ctx.warn("new_version", f"File version {v} is newer than the latest tested ({MAX_TESTED_VERSION})")
        return SourceInfo(
            format=self.format_id,
            format_version=version,
            # KiCad 5 writes (host pcbnew 5.1.12) instead of generator/generator_version.
            generator=root.atom("generator") or root.atom("host"),
            generator_version=root.atom("generator_version") or root.atom("host", 1),
            filename=filename,
            sha256=hashlib.sha256(data).hexdigest(),
            size_bytes=len(data),
        )

    def _layers(self, root: SExpr, ctx: _Context) -> list[Layer]:
        node = root.child("layers")
        layers: list[Layer] = []
        if node is None:
            ctx.warn("missing_layers", "No layer table; assuming a two-layer board")
            for idx, name in ((0, "F.Cu"), (31, "B.Cu"), (44, "Edge.Cuts")):
                kind, side = _layer_kind(name)
                layers.append(Layer(index=idx, name=name, kind=kind, side=side))
            return layers
        for entry in node.args:
            if not isinstance(entry, SExpr) or len(entry) < 2:
                continue
            atoms = [a for a in entry if not isinstance(a, SExpr)]
            try:
                index = int(atoms[0])
            except ValueError:
                continue
            name = atoms[1]
            kind, side = _layer_kind(name)
            layers.append(
                Layer(
                    index=index,
                    name=name,
                    kind=kind,
                    side=side,
                    source_type=atoms[2] if len(atoms) > 2 else None,
                    user_name=atoms[3] if len(atoms) > 3 else None,
                )
            )
        return layers

    def _nets(self, root: SExpr, ctx: _Context) -> list[Net]:
        nets: list[Net] = []
        for node in root.children("net"):
            atoms = node.atoms()
            if len(atoms) < 2 or not _NUM_RE.match(atoms[0]):
                continue
            code, name = int(atoms[0]), atoms[1]
            ctx.net_by_code[code] = name
            if code != 0 and name:
                nets.append(Net(code=code, name=name))
        if not ctx.net_by_code:
            # KiCad 10+ may drop the net table; collect names from pads/tracks later.
            names: dict[str, None] = {}
            for fp in root.children():
                if fp.name in {"footprint", "module"}:
                    for pad in fp.children("pad"):
                        n = ctx.resolve_net(pad)
                        if n:
                            names[n] = None
            nets = [Net(code=i + 1, name=n) for i, n in enumerate(names)]
        return nets

    def _component(self, node: SExpr, ctx: _Context) -> Component:
        atoms = node.atoms()
        footprint = next((a for a in atoms if a not in {"locked", "placed"}), "") or ""
        at = node.numbers("at")
        origin: geo.Vec = (at[0], at[1]) if len(at) >= 2 else (0.0, 0.0)
        rotation = at[2] if len(at) >= 3 else 0.0
        layer = node.atom("layer") or "F.Cu"
        side = Side.BOTTOM if layer.startswith("B.") else Side.TOP

        properties: dict[str, str] = {}
        for prop in node.children("property"):
            pa = prop.atoms()
            if len(pa) >= 2 and pa[1]:
                properties[pa[0]] = pa[1]
        for text in node.children("fp_text"):
            ta = text.atoms()
            if len(ta) >= 2 and ta[0] in {"reference", "value"}:
                properties.setdefault(ta[0].capitalize(), ta[1])

        attr = node.child("attr")
        attributes = [str(a) for a in attr.atoms()] if attr is not None else []

        pads = [self._pad(p, origin, rotation, ctx) for p in node.children("pad")]
        graphics = [
            g
            for child in node.children()
            if child.name
            and child.name.startswith("fp_")
            and (g := self._graphic(child, ctx, origin=(origin, rotation))) is not None
        ]
        reference = properties.get("Reference", "")
        if not reference:
            ctx.warn("missing_reference", f"Footprint '{footprint}' has no reference designator")
        return Component(
            reference=reference,
            value=properties.get("Value"),
            footprint=footprint,
            layer=layer,
            side=side,
            position=_pt(origin),
            rotation=rotation,
            attributes=attributes,
            properties={k: v for k, v in properties.items() if k not in {"Reference", "Value"}},
            pads=pads,
            graphics=graphics,
            uuid=node.atom("uuid") or node.atom("tstamp"),
        )

    def _pad(self, node: SExpr, origin: geo.Vec, fp_rot: float, ctx: _Context) -> Pad:
        atoms = node.atoms()
        number = atoms[0] if atoms else ""
        raw_type = atoms[1] if len(atoms) > 1 else "smd"
        shape = atoms[2] if len(atoms) > 2 else "rect"
        pad_type = _PAD_TYPES.get(raw_type)
        if pad_type is None:
            ctx.warn("unknown_pad_type", f"Unknown pad type '{raw_type}', treated as SMD")
            pad_type = PadType.SMD
        at = node.numbers("at")
        local = (at[0], at[1]) if len(at) >= 2 else (0.0, 0.0)
        # KiCad stores the pad angle as absolute (already includes footprint rotation).
        rotation = at[2] if len(at) >= 3 else fp_rot
        size = node.numbers("size")
        drill = None
        drill_node = node.child("drill")
        if drill_node is not None:
            nums = [float(a) for a in drill_node.atoms() if _is_number(a)]
            offset = _xy(drill_node.child("offset"))
            if nums:
                drill = Drill(
                    diameter=nums[0],
                    slot_length=nums[1] if drill_node.has_atom("oval") and len(nums) > 1 else None,
                    offset=_pt(offset) if offset and offset != (0.0, 0.0) else None,
                )
        layers_node = node.child("layers")
        layers = ctx.expand_layers(layers_node.atoms()) if layers_node is not None else []
        return Pad(
            number=number,
            type=pad_type,
            shape=shape,
            position=_pt(geo.to_board(local, origin, fp_rot)),
            rotation=rotation,
            size=Point(x=size[0] if size else 0.0, y=size[1] if len(size) > 1 else (size[0] if size else 0.0)),
            layers=layers,
            net=ctx.resolve_net(node),
            drill=drill,
        )

    def _graphic(
        self,
        node: SExpr,
        ctx: _Context,
        origin: tuple[geo.Vec, float] | None,
    ) -> Graphic | None:
        kind = node.name.split("_", 1)[1] if node.name else ""
        layer = node.atom("layer")
        if layer is None:
            return None

        def tf(p: geo.Vec) -> geo.Vec:
            return geo.to_board(p, origin[0], origin[1]) if origin else p

        width = _stroke_width(node)
        filled = _is_filled(node)
        start, end = _xy(node.child("start")), _xy(node.child("end"))
        pts: list[geo.Vec]
        if kind == "line" and start and end:
            out_kind, pts = "line", [start, end]
        elif kind == "arc" and start and end:
            mid = _xy(node.child("mid"))
            if mid is None:  # legacy: start=centre, end=arc start, angle=sweep
                angle = node.number("angle", default=0.0) or 0.0
                mid, arc_end = geo.arc_mid_from_center(end, start, angle)
                pts = [end, mid, arc_end]
            else:
                pts = [start, mid, end]
            out_kind = "arc"
        elif kind == "circle":
            center = _xy(node.child("center")) or start
            if center is None or end is None:
                return None
            out_kind, pts = "circle", [center, end]
        elif kind == "rect" and start and end:
            out_kind, pts = "rect", [start, end]
        elif kind == "poly":
            pts = _poly_points(node.child("pts"))
            if len(pts) < 2:
                return None
            out_kind = "polygon"
        elif kind in {"text", "text_box"}:
            return None
        elif kind in {"curve"}:
            ctx.warn("unsupported_curve", f"Bezier curve on layer {layer} is not supported and was skipped")
            return None
        else:
            return None

        if out_kind == "rect" and origin and origin[1]:
            # A rotated footprint rectangle is no longer axis-aligned: emit a polygon.
            (x1, y1), (x2, y2) = pts
            pts = [tf(p) for p in ((x1, y1), (x2, y1), (x2, y2), (x1, y2))]
            out_kind = "polygon"
        else:
            pts = [tf(p) for p in pts]
        return Graphic(kind=out_kind, layer=layer, width=width, points=[_pt(p) for p in pts], filled=filled)

    def _tracks(self, root: SExpr, ctx: _Context) -> list[Track]:
        tracks: list[Track] = []
        for node in root.children():
            if node.name not in {"segment", "arc"}:
                continue
            start, end = _xy(node.child("start")), _xy(node.child("end"))
            if start is None or end is None:
                ctx.warn("invalid_track", "Track without start/end point skipped")
                continue
            mid = _xy(node.child("mid")) if node.name == "arc" else None
            length = geo.arc_length(start, mid, end) if mid else geo.distance(start, end)
            tracks.append(
                Track(
                    kind="arc" if mid else "segment",
                    start=_pt(start),
                    end=_pt(end),
                    mid=_pt(mid) if mid else None,
                    width=node.number("width", default=0.0) or 0.0,
                    layer=node.atom("layer") or "",
                    net=ctx.resolve_net(node),
                    length=round(length, 6),
                )
            )
        return tracks

    def _via(self, node: SExpr, ctx: _Context) -> Via:
        at = _xy(node.child("at")) or (0.0, 0.0)
        via_type = "through"
        if node.has_atom("blind"):
            via_type = "blind"
        elif node.has_atom("micro"):
            via_type = "micro"
        layers_node = node.child("layers")
        layers = ctx.expand_layers(layers_node.atoms()) if layers_node is not None else ["F.Cu", "B.Cu"]
        return Via(
            position=_pt(at),
            diameter=node.number("size", default=0.0) or 0.0,
            drill=node.number("drill", default=0.0) or 0.0,
            layers=layers,
            net=ctx.resolve_net(node),
            via_type=via_type,
        )

    def _zone(self, node: SExpr, ctx: _Context) -> Zone | None:
        polygon = node.child("polygon")
        outline = _poly_points(polygon.child("pts")) if polygon is not None else []
        if len(outline) < 3:
            ctx.warn("invalid_zone", "Zone without a valid outline polygon skipped")
            return None
        layers_node = node.child("layers")
        if layers_node is not None:
            layers = ctx.expand_layers(layers_node.atoms())
        else:
            layer = node.atom("layer")
            layers = [layer] if layer else []
        net_name = node.atom("net_name") or None
        return Zone(
            net=net_name or ctx.resolve_net(node),
            layers=layers,
            outline=[_pt(p) for p in outline],
            area=round(geo.polygon_area(outline), 6),
            filled=node.child("filled_polygon") is not None,
            keepout=node.child("keepout") is not None,
            name=node.atom("name"),
        )

    def _outline(self, graphics: list[Graphic], ctx: _Context) -> BoardOutline:
        if not graphics:
            ctx.warn("missing_outline", "No board outline found on Edge.Cuts")
            return BoardOutline()
        edges: list[geo.OutlineEdge] = []
        bbox = geo.BBox()
        for g in graphics:
            p = [(pt.x, pt.y) for pt in g.points]
            if g.kind == "line":
                edges.append(geo.OutlineEdge(p))
            elif g.kind == "arc":
                edges.append(geo.OutlineEdge(geo.sample_arc(p[0], p[1], p[2])))
            elif g.kind == "circle":
                edges.append(geo.OutlineEdge(geo.sample_circle(p[0], geo.distance(p[0], p[1])), closed=True))
            elif g.kind == "rect":
                (x1, y1), (x2, y2) = p
                edges.append(geo.OutlineEdge([(x1, y1), (x2, y1), (x2, y2), (x1, y2)], closed=True))
            elif g.kind == "polygon":
                edges.append(geo.OutlineEdge(p, closed=True))
        for e in edges:
            bbox.extend(e.points)
        result = geo.assemble_outline(edges)
        if not result.closed:
            ctx.warn(
                "open_outline",
                f"Board outline is not closed ({result.open_chains} open chain(s)); area not computed",
            )
        area = result.area if result.closed else None
        return BoardOutline(
            graphics=graphics,
            closed=result.closed,
            bbox=_bbox(bbox),
            area=round(area, 6) if area is not None else None,
        )

    def _constraints(self, root: SExpr) -> DesignConstraints:
        general = root.child("general")
        setup = root.child("setup")
        net_classes: list[NetClass] = []
        for nc in root.children("net_class"):
            atoms = nc.atoms()
            if not atoms:
                continue
            net_classes.append(
                NetClass(
                    name=atoms[0],
                    clearance=nc.number("clearance"),
                    track_width=nc.number("trace_width"),
                    via_diameter=nc.number("via_dia"),
                    via_drill=nc.number("via_drill"),
                    nets=[a for n in nc.children("add_net") for a in n.atoms()[:1]],
                )
            )
        return DesignConstraints(
            board_thickness=general.number("thickness") if general is not None else None,
            pad_to_mask_clearance=setup.number("pad_to_mask_clearance") if setup is not None else None,
            solder_mask_min_width=setup.number("solder_mask_min_width") if setup is not None else None,
            pad_to_paste_clearance=setup.number("pad_to_paste_clearance") if setup is not None else None,
            net_classes=net_classes,
        )

    def _content_bbox(self, components, tracks, vias, graphics) -> BoundingBox | None:
        bbox = geo.BBox()
        for c in components:
            bbox.add((c.position.x, c.position.y))
            for p in c.pads:
                bbox.add((p.position.x, p.position.y), max(p.size.x, p.size.y) / 2)
        for t in tracks:
            bbox.extend([(t.start.x, t.start.y), (t.end.x, t.end.y)], t.width / 2)
        for v in vias:
            bbox.add((v.position.x, v.position.y), v.diameter / 2)
        for g in graphics:
            bbox.extend((p.x, p.y) for p in g.points)
        return _bbox(bbox)

    def _stats(self, ctx, nets, components, tracks, vias, zones, outline, constraints):
        per_net: dict[str, NetStat] = {n.name: NetStat(name=n.name) for n in nets}

        def ns(name: str | None) -> NetStat | None:
            if not name:
                return None
            if name not in per_net:
                per_net[name] = NetStat(name=name)
            return per_net[name]

        pads = [p for c in components for p in c.pads]
        unconnected = 0
        for p in pads:
            s = ns(p.net)
            if s:
                s.pad_count += 1
            elif p.type != PadType.NPTH and any(layer.endswith(".Cu") for layer in p.layers):
                unconnected += 1
        for t in tracks:
            s = ns(t.net)
            if s:
                s.track_count += 1
                s.track_length += t.length
        for v in vias:
            s = ns(v.net)
            if s:
                s.via_count += 1
        for s in per_net.values():
            s.track_length = round(s.track_length, 4)

        bbox = outline.bbox
        stats = DesignStats(
            layer_count=len(ctx.layers),
            copper_layer_count=len(ctx.copper_layers),
            net_count=len(nets),
            component_count=len(components),
            pad_count=len(pads),
            smd_pad_count=sum(p.type == PadType.SMD for p in pads),
            through_hole_pad_count=sum(p.type == PadType.THROUGH_HOLE for p in pads),
            track_count=len(tracks),
            via_count=len(vias),
            zone_count=len(zones),
            total_track_length=round(sum(t.length for t in tracks), 4),
            board_width=round(bbox.width, 4) if bbox else None,
            board_height=round(bbox.height, 4) if bbox else None,
            board_area=outline.area,
            board_thickness=constraints.board_thickness,
            min_track_width=min((t.width for t in tracks if t.width > 0), default=None),
            min_via_drill=min((v.drill for v in vias if v.drill > 0), default=None),
            min_via_diameter=min((v.diameter for v in vias if v.diameter > 0), default=None),
            components_top=sum(c.side == Side.TOP for c in components),
            components_bottom=sum(c.side == Side.BOTTOM for c in components),
            unconnected_pad_count=unconnected,
        )
        return stats, sorted(per_net.values(), key=lambda s: s.name)


def _is_number(token: str) -> bool:
    try:
        float(token)
    except ValueError:
        return False
    return True


def _poly_points(pts: SExpr | None) -> list[geo.Vec]:
    if pts is None:
        return []
    out: list[geo.Vec] = []
    for item in pts.children():
        if item.name == "xy":
            p = _xy(item)
            if p:
                out.append(p)
        elif item.name == "arc":
            s, m, e = _xy(item.child("start")), _xy(item.child("mid")), _xy(item.child("end"))
            if s and m and e:
                seg = geo.sample_arc(s, m, e)
                out.extend(seg[1:] if out and out[-1] == s else seg)
    return out


def _bbox(b: geo.BBox) -> BoundingBox | None:
    if b.empty:
        return None
    return BoundingBox(
        min_x=round(b.min_x, 6), min_y=round(b.min_y, 6), max_x=round(b.max_x, 6), max_y=round(b.max_y, 6)
    )
