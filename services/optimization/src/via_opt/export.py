"""Export accepted changes by patching the original KiCad file, then prove the patch is right.

``via_pcb.patch`` edits only the target nodes' text. Here the patched board is parsed again and
compared with ``apply(original, changes)``: every changed object must match what the change says,
and every other object must be exactly as it was. Any mismatch fails the export; VIA never hands
out a file it hasn't verified.
"""

from __future__ import annotations

import gc
import math
from dataclasses import dataclass, field

from via_opt.changes import Change, apply
from via_pcb.adapters.kicad import KiCadAdapter
from via_pcb.models import PCBDesign
from via_pcb.patch import board_of, parse_with_spans, patch_board, replace_board_member

TOL = 1e-4  # mm: patched numbers are written with 6 decimals


class ExportVerificationError(ValueError):
    def __init__(self, problems: list[str]) -> None:
        super().__init__("; ".join(problems[:5]))
        self.problems = problems


@dataclass
class ExportResult:
    data: bytes
    board: bytes
    applied: list[int] = field(default_factory=list)
    refused: list[tuple[int, str]] = field(default_factory=list)
    board_member: str | None = None


def _near(a: float, b: float) -> bool:
    return math.isclose(a, b, abs_tol=TOL)


def _angle_near(a: float, b: float) -> bool:
    d = (a - b) % 360
    return min(d, 360 - d) < 1e-3


@dataclass
class Digest:
    """What verification compares, as plain tuples: far smaller than the design on large boards."""

    counts: tuple[int, ...]
    components: list[tuple[str, str, float, float, float, tuple[tuple[str, float, float, float], ...]]]
    tracks: list[tuple[str, float, float, float, float, float, str, str | None]]
    vias: list[tuple[str, float, float, float, float, str | None]]
    outline: tuple[tuple[float, float, float, float] | None, bool]


def digest(d: PCBDesign) -> Digest:
    bb = d.outline.bbox
    return Digest(
        counts=(len(d.components), len(d.tracks), len(d.vias), len(d.zones), len(d.nets)),
        components=[
            (c.reference or c.id or "", c.reference, c.position.x, c.position.y, c.rotation,
             tuple((p.number, p.position.x, p.position.y, p.rotation) for p in c.pads))
            for c in d.components
        ],
        tracks=[(t.id or "", t.width, t.start.x, t.start.y, t.end.x, t.end.y, t.layer, t.net) for t in d.tracks],
        vias=[(v.id or "", v.position.x, v.position.y, v.diameter, v.drill, v.net) for v in d.vias],
        outline=((bb.min_x, bb.min_y, bb.max_x, bb.max_y) if bb else None, d.outline.closed),
    )  # fmt: skip


def compare(expected: PCBDesign | Digest, actual: PCBDesign | Digest) -> list[str]:
    """Differences between the design a change set should produce and the one the patch produced."""
    e = expected if isinstance(expected, Digest) else digest(expected)
    a = actual if isinstance(actual, Digest) else digest(actual)
    names = ("components", "tracks", "vias", "zones", "nets")
    problems = [f"{n} count changed" for n, x, y in zip(names, e.counts, a.counts, strict=True) if x != y]
    if problems:
        return problems
    for (label, ref, ex, ey, erot, epads), (_, aref, ax, ay, arot, apads) in zip(
        e.components, a.components, strict=True
    ):
        if ref != aref:
            problems.append(f"component order changed at {label}")
            continue
        if not (_near(ex, ax) and _near(ey, ay)):
            problems.append(f"{label} position ({ax}, {ay}) != ({ex}, {ey})")
        if not _angle_near(erot, arot):
            problems.append(f"{label} rotation {arot} != {erot}")
        for (num, px, py, prot), (_, qx, qy, qrot) in zip(epads, apads, strict=True):
            if not (_near(px, qx) and _near(py, qy)):
                problems.append(f"{label} pad {num} position ({qx}, {qy}) != ({px}, {py})")
            if not _angle_near(prot, qrot):
                problems.append(f"{label} pad {num} rotation {qrot} != {prot}")
    for et, at in zip(e.tracks, a.tracks, strict=True):
        if not all(_near(x, y) for x, y in zip(et[1:6], at[1:6], strict=True)) or et[6:] != at[6:]:
            problems.append(f"track {et[0]} differs")
    for ev, av in zip(e.vias, a.vias, strict=True):
        if not all(_near(x, y) for x, y in zip(ev[1:5], av[1:5], strict=True)) or ev[5] != av[5]:
            problems.append(f"via {ev[0]} differs")
    (eb, eclosed), (ab, aclosed) = e.outline, a.outline
    if (eb is None) != (ab is None) or (
        eb is not None and ab is not None and not all(_near(x, y) for x, y in zip(eb, ab, strict=True))
    ):
        problems.append("board outline differs")
    if eclosed != aclosed:
        problems.append("board outline closure differs")
    return problems


def export_changes(data: bytes, filename: str | None, changes: list[Change]) -> ExportResult:
    """Patch ``data`` (a board or project archive) with ``changes`` and verify the result."""
    board, member = board_of(data, filename)
    # Large boards: parse once (one tree shared by the patcher and the adapter), then keep only a
    # compact digest of the expected result before re-parsing the patched file, so a single full
    # board is in memory at any time.
    text, root, original = parse_with_spans(board)
    patched = patch_board(board, [c.model_dump(mode="json") for c in changes], design=original, parsed=(text, root))
    del text, root
    expected = digest(apply(original, [changes[i] for i in patched.applied], copy=False))
    del original
    gc.collect()
    actual = digest(KiCadAdapter().parse(patched.data, filename="board.kicad_pcb"))
    problems = compare(expected, actual)
    if problems:
        raise ExportVerificationError(problems)
    out = replace_board_member(data, member, patched.data) if member else patched.data
    return ExportResult(
        data=out, board=patched.data, applied=patched.applied, refused=patched.refused, board_member=member
    )
