"""Apply explicit changes to the *original* KiCad file by editing it in place.

VIA never regenerates a board from its normalized model (which deliberately leaves things out).
The patcher parses the file with source spans, finds each change's target node (by UUID, or by its
position among the parsed objects when the file has no UUIDs), and rewrites only that node's text.
Every byte outside the edited spans is preserved, including KiCad version, formatting, comments and
everything VIA doesn't model.

Supported: ``move_component``, ``rotate_component``, ``set_track_width``, ``move_via``, ``set_via_size``,
``set_outline_rect`` (line or rectangle outlines made of top-level Edge.Cuts graphics). Anything else,
or any change whose target can't be found unambiguously, is refused with a reason, never approximated.
"""

from __future__ import annotations

import io
import uuid
import zipfile
from dataclasses import dataclass, field
from typing import Any

from via_pcb.adapters.kicad import KiCadAdapter
from via_pcb.models import PCBDesign
from via_pcb.parser import SExpr, SpannedSExpr, parse_sexpr
from via_pcb.project import is_project_archive, read_project, select_project

SUPPORTED = {"move_component", "rotate_component", "set_track_width", "move_via", "set_via_size", "set_outline_rect"}


@dataclass
class PatchResult:
    data: bytes
    applied: list[int] = field(default_factory=list)
    refused: list[tuple[int, str]] = field(default_factory=list)
    board_member: str | None = None


def fmt(v: float) -> str:
    out = f"{float(v):.6f}".rstrip("0").rstrip(".")
    return "0" if out in ("-0", "") else out


def _span(node: SExpr) -> tuple[int, int]:
    assert isinstance(node, SpannedSExpr)
    return node.start, node.end


@dataclass
class _Index:
    components: dict[str, SExpr]
    tracks: dict[str, SExpr]
    vias: dict[str, SExpr]
    edge_nodes: list[SExpr]
    outline_graphics: int
    version: int | None


def _index(text: str, root: SExpr, design: PCBDesign | None = None) -> _Index:
    """Map VIA's stable ids to source nodes (the adapter assigns ids in file order)."""
    design = design or KiCadAdapter().parse(text.encode(), filename="board.kicad_pcb")
    fps = [n for n in root.children() if n.name in {"footprint", "module"}]
    trk = [
        n
        for n in root.children()
        if n.name in {"segment", "arc"} and n.child("start") is not None and n.child("end") is not None
    ]
    vias = list(root.children("via"))
    if len(fps) != len(design.components) or len(trk) != len(design.tracks) or len(vias) != len(design.vias):
        raise ValueError("The file's objects don't line up with VIA's parse; refusing to patch.")
    edges = [n for n in root.children() if n.name and n.name.startswith("gr_") and n.atom("layer") == "Edge.Cuts"]
    version = root.atom("version")
    return _Index(
        components={c.id: n for c, n in zip(design.components, fps, strict=True) if c.id},
        tracks={t.id: n for t, n in zip(design.tracks, trk, strict=True) if t.id},
        vias={v.id: n for v, n in zip(design.vias, vias, strict=True) if v.id},
        edge_nodes=edges, outline_graphics=len(design.outline.graphics),
        version=int(version) if version and version.isdigit() else None,
    )  # fmt: skip


def _replace_child(text: str, node: SExpr, name: str, replacement: str) -> tuple[int, int, str] | None:
    child = node.child(name)
    if child is None:
        return None
    s, e = _span(child)
    return s, e, replacement


def _edits_for(text: str, idx: _Index, change: dict[str, Any]) -> list[tuple[int, int, str]]:
    kind = change["kind"]
    target = change.get("target", {})
    after = change.get("after", {})
    tid = target.get("id", "")
    if kind == "move_component":
        node = idx.components.get(tid)
        if node is None:
            raise LookupError(f"component {target.get('label') or tid} not found")
        at = node.child("at")
        if at is None:
            raise LookupError("footprint has no (at ...)")
        atoms = at.atoms()
        angle = f" {atoms[2]}" if len(atoms) > 2 else ""
        s, e = _span(at)
        return [(s, e, f"(at {fmt(after['x'])} {fmt(after['y'])}{angle})")]
    if kind == "rotate_component":
        node = idx.components.get(tid)
        if node is None:
            raise LookupError(f"component {target.get('label') or tid} not found")
        at = node.child("at")
        if at is None:
            raise LookupError("footprint has no (at ...)")
        nums = at.atoms()
        old = float(nums[2]) if len(nums) > 2 else 0.0
        new = float(after["rotation"]) % 360
        delta = new - old
        s, e = _span(at)
        out = [(s, e, f"(at {nums[0]} {nums[1]}{'' if new == 0 else ' ' + fmt(new)})")]
        # Pad and text angles are stored absolute (footprint + own rotation): turn them too.
        for child in node.children():
            if child.name not in {"pad", "fp_text", "property"}:
                continue
            cat = child.child("at")
            if cat is None:
                continue
            a = cat.atoms()
            if len(a) < 2:
                continue
            ang = ((float(a[2]) if len(a) > 2 and _is_num(a[2]) else 0.0) + delta) % 360
            rest = " ".join(a[3:] if len(a) > 2 and _is_num(a[2]) else a[2:])
            cs, ce = _span(cat)
            text_ang = "" if ang == 0 and child.name == "pad" else f" {fmt(ang)}"
            out.append((cs, ce, f"(at {a[0]} {a[1]}{text_ang}{' ' + rest if rest else ''})"))
        return out
    if kind == "set_track_width":
        node = idx.tracks.get(tid)
        if node is None:
            raise LookupError(f"track {tid} not found")
        edit = _replace_child(text, node, "width", f"(width {fmt(after['width'])})")
        if edit is None:
            raise LookupError("track has no (width ...)")
        return [edit]
    if kind == "move_via":
        node = idx.vias.get(tid)
        if node is None:
            raise LookupError(f"via {tid} not found")
        edit = _replace_child(text, node, "at", f"(at {fmt(after['x'])} {fmt(after['y'])})")
        if edit is None:
            raise LookupError("via has no (at ...)")
        return [edit]
    if kind == "set_via_size":
        node = idx.vias.get(tid)
        if node is None:
            raise LookupError(f"via {tid} not found")
        size = node.child("size")
        if size is None:
            raise LookupError("via has no (size ...)")
        drill = node.child("drill")
        s, e = _span(size)
        if drill is None:  # KiCad 5 omits a default drill: write it explicitly now
            return [(s, e, f"(size {fmt(after['diameter'])}) (drill {fmt(after['drill'])})")]
        ds, de = _span(drill)
        return [(s, e, f"(size {fmt(after['diameter'])})"), (ds, de, f"(drill {fmt(after['drill'])})")]
    if kind == "set_outline_rect":
        if not idx.edge_nodes or len(idx.edge_nodes) != idx.outline_graphics:
            raise LookupError("the outline includes footprint edges or isn't made of board graphics")
        x1, y1, x2, y2 = (float(after[k]) for k in ("min_x", "min_y", "max_x", "max_y"))
        # The new outline replaces every board Edge.Cuts graphic, written in the file's own style:
        # a copy of its first rectangle, or four copies of its first line.
        first = next((n for n in idx.edge_nodes if n.name in {"gr_rect", "gr_line"}), None)
        if first is None:
            raise LookupError("the outline has no line or rectangle to use as a template")
        fs, fe = _span(first)
        original = text[fs:fe]
        if first.name == "gr_rect":
            body = _sub_points(original, first, [((x1, y1), (x2, y2))])[0]
        else:
            corners = [(x1, y1), (x2, y1), (x2, y2), (x1, y2)]
            sides = [(corners[i], corners[(i + 1) % 4]) for i in range(4)]
            sep = text[_line_start(text, fs) : fs]
            body = ("\n" + sep).join(_sub_points(original, first, sides))
        edits = [(fs, fe, body)]
        for n in idx.edge_nodes:
            if n is first:
                continue
            s, e = _span(n)
            ls = _line_start(text, s)
            blank_before = text[ls:s].strip() == "" and ls > 0
            edits.append((ls - 1 if blank_before else s, e, ""))  # drop the line with it
        return edits
    raise LookupError(f"{kind} isn't supported for export")


def _is_num(tok: str) -> bool:
    try:
        float(tok)
    except ValueError:
        return False
    return True


def _new_id(old: str) -> str:
    """A fresh identifier in the same style as ``old`` (KiCad 5 tstamps are 8 hex digits)."""
    bare = old.strip('"')
    return uuid.uuid4().hex[:8].upper() if len(bare) == 8 else str(uuid.uuid4())


def _line_start(text: str, pos: int) -> int:
    return text.rfind("\n", 0, pos) + 1


def _sub_points(
    original: str, node: SExpr, segments: list[tuple[tuple[float, float], tuple[float, float]]]
) -> list[str]:
    """Copies of ``original`` (a gr_line/gr_rect) with new start/end points and fresh UUIDs."""
    base = node.start  # type: ignore[attr-defined]
    start, end = node.child("start"), node.child("end")
    ident = node.child("uuid") or node.child("tstamp")
    out = []
    for (ax, ay), (bx, by) in segments:
        edits = []
        for child, (x, y) in ((start, (ax, ay)), (end, (bx, by))):
            assert child is not None
            s, e = _span(child)
            edits.append((s - base, e - base, f"({child.name} {fmt(x)} {fmt(y)})"))
        if ident is not None:
            s, e = _span(ident)
            old = ident.atoms()[0] if ident.atoms() else ""
            quoted = '"' if '"' in original[s - base : e - base] else ""
            edits.append((s - base, e - base, f"({ident.name} {quoted}{_new_id(old)}{quoted})"))
        piece = original
        for s, e, rep in sorted(edits, reverse=True):
            piece = piece[:s] + rep + piece[e:]
        out.append(piece)
    return out


def parse_with_spans(data: bytes) -> tuple[str, SExpr, PCBDesign]:
    """One parse of ``data`` giving the text, the spanned tree and VIA's design built from that tree."""
    text = data.decode("utf-8")
    root = parse_sexpr(text, spans=True)
    return text, root, KiCadAdapter().from_tree(root, data, "board.kicad_pcb")


def patch_board(
    data: bytes,
    changes: list[dict[str, Any]],
    design: PCBDesign | None = None,
    parsed: tuple[str, SExpr] | None = None,
) -> PatchResult:
    """``design`` and ``parsed`` (text, spanned tree) are VIA's parse of exactly ``data`` when the
    caller already has them; passing them avoids parsing a large board again."""
    text, root = parsed if parsed is not None else (data.decode("utf-8"), parse_sexpr(data.decode("utf-8"), spans=True))
    idx = _index(text, root, design)
    edits: list[tuple[int, int, str]] = []
    result = PatchResult(data=b"")
    for i, change in enumerate(changes):
        if change.get("kind") not in SUPPORTED:
            result.refused.append((i, f"{change.get('kind')} isn't supported for export"))
            continue
        try:
            new = _edits_for(text, idx, change)
        except (LookupError, KeyError, ValueError) as exc:
            result.refused.append((i, str(exc)))
            continue
        if any(not (e <= s0 or s >= e0) for s, e, _ in new for s0, e0, _ in edits):
            result.refused.append((i, "conflicts with another change to the same object"))
            continue
        edits.extend(new)
        result.applied.append(i)
    for s, e, rep in sorted(edits, key=lambda x: x[0], reverse=True):
        text = text[:s] + rep + text[e:]
    result.data = text.encode("utf-8")
    return result


def replace_board_member(archive: bytes, board_name: str, board: bytes) -> bytes:
    """A copy of a project archive with only its board member replaced (order and metadata kept)."""
    zf, _ = select_project(archive)
    buf = io.BytesIO()
    with zf, zipfile.ZipFile(buf, "w") as out:
        for info in zf.infolist():
            same = info.filename.replace("\\", "/") == board_name
            out.writestr(info, board if same else zf.read(info))
    return buf.getvalue()


def board_of(data: bytes, filename: str | None) -> tuple[bytes, str | None]:
    """The board text of an upload, and its member name when it is a project archive."""
    if not is_project_archive(filename, data[:8]):
        return data, None
    files = read_project(data)
    return files.board, files.board_name


def patch_source(data: bytes, filename: str | None, changes: list[dict[str, Any]]) -> PatchResult:
    """Patch a board file, or the board inside a KiCad project archive (other members kept as they were)."""
    board, member = board_of(data, filename)
    result = patch_board(board, changes)
    if member is not None:
        result.data = replace_board_member(data, member, result.data)
        result.board_member = member
    return result
