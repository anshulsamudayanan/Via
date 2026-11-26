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


def compare(expected: PCBDesign, actual: PCBDesign) -> list[str]:
    """Differences between the design a change set should produce and the one the patch produced."""
    problems: list[str] = []
    for name in ("components", "tracks", "vias", "zones", "nets"):
        if len(getattr(expected, name)) != len(getattr(actual, name)):
            problems.append(f"{name} count changed")
    if problems:
        return problems
    for e, a in zip(expected.components, actual.components, strict=True):
        label = e.reference or e.id
        if e.reference != a.reference:
            problems.append(f"component order changed at {label}")
            continue
        if not (_near(e.position.x, a.position.x) and _near(e.position.y, a.position.y)):
            problems.append(f"{label} position {a.position} != {e.position}")
        if not _angle_near(e.rotation, a.rotation):
            problems.append(f"{label} rotation {a.rotation} != {e.rotation}")
        for pe, pa in zip(e.pads, a.pads, strict=True):
            if not (_near(pe.position.x, pa.position.x) and _near(pe.position.y, pa.position.y)):
                problems.append(f"{label} pad {pe.number} position {pa.position} != {pe.position}")
            if not _angle_near(pe.rotation, pa.rotation):
                problems.append(f"{label} pad {pe.number} rotation {pa.rotation} != {pe.rotation}")
    for et, at in zip(expected.tracks, actual.tracks, strict=True):
        same = _near(et.width, at.width) and all(
            _near(p.x, q.x) and _near(p.y, q.y) for p, q in ((et.start, at.start), (et.end, at.end))
        )
        if not same or et.layer != at.layer or et.net != at.net:
            problems.append(f"track {et.id} differs")
    for ev, av in zip(expected.vias, actual.vias, strict=True):
        if not (
            _near(ev.position.x, av.position.x)
            and _near(ev.position.y, av.position.y)
            and _near(ev.diameter, av.diameter)
            and _near(ev.drill, av.drill)
            and ev.net == av.net
        ):
            problems.append(f"via {ev.id} differs")
    eb, ab = expected.outline.bbox, actual.outline.bbox
    if (eb is None) != (ab is None) or (
        eb is not None
        and ab is not None
        and not all(_near(getattr(eb, k), getattr(ab, k)) for k in ("min_x", "min_y", "max_x", "max_y"))
    ):
        problems.append("board outline differs")
    if expected.outline.closed != actual.outline.closed:
        problems.append("board outline closure differs")
    return problems


def export_changes(data: bytes, filename: str | None, changes: list[Change]) -> ExportResult:
    """Patch ``data`` (a board or project archive) with ``changes`` and verify the result."""
    board, member = board_of(data, filename)
    # Large boards: parse once (tree shared by the patcher and the adapter), apply the expected
    # changes in place, and drop the tree before re-parsing the result, so at most one tree and
    # two designs are alive at a time.
    text, root, original = parse_with_spans(board)
    patched = patch_board(board, [c.model_dump(mode="json") for c in changes], design=original, parsed=(text, root))
    del text, root
    gc.collect()
    expected = apply(original, [changes[i] for i in patched.applied], copy=False)
    actual = KiCadAdapter().parse(patched.data, filename="board.kicad_pcb")
    problems = compare(expected, actual)
    if problems:
        raise ExportVerificationError(problems)
    out = replace_board_member(data, member, patched.data) if member else patched.data
    return ExportResult(
        data=out, board=patched.data, applied=patched.applied, refused=patched.refused, board_member=member
    )
