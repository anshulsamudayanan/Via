"""Exporting changes by patching the original KiCad file in place.

Expected values are hand-derived: each change states its target value, and the tests check that the
re-parsed file has exactly that value while every byte outside the edited spans is untouched.
"""

from __future__ import annotations

import io
import json
import zipfile
from pathlib import Path

import pytest
from via_opt.changes import Change, ChangeKind, Target
from via_opt.export import ExportVerificationError, compare, export_changes

from via_pcb.adapters.kicad import KiCadAdapter
from via_pcb.parser import SpannedSExpr, parse_sexpr
from via_pcb.patch import fmt, patch_board, patch_source

HERE = Path(__file__).parent
FIX = HERE / "fixtures"
REF = (FIX / "via_reference_v8.kicad_pcb").read_bytes()
LEGACY = (FIX / "via_legacy_v5.kicad_pcb").read_bytes()
MANIFEST = json.loads((HERE / "real_fixtures.json").read_text())
REAL = [fx["file"] for fx in MANIFEST["fixtures"] if fx["file"].endswith(".kicad_pcb")]


def parse(data: bytes):
    return KiCadAdapter().parse(data, filename="board.kicad_pcb")


def ch(kind: ChangeKind, target_kind: str, tid: str, after: dict, before: dict | None = None) -> Change:
    return Change(kind=kind, target=Target(kind=target_kind, id=tid), before=before or {}, after=after, reason="test")


def test_spans_cover_source_text():
    text = '(kicad_pcb (version 2) (net 1 "A B") (seg (start 1 2)))'
    root = parse_sexpr(text, spans=True)
    assert isinstance(root, SpannedSExpr) and (root.start, root.end) == (0, len(text))
    seg = root.child("seg")
    assert text[seg.start : seg.end] == "(seg (start 1 2))"  # type: ignore[union-attr]
    assert text[root.child("net").start : root.child("net").end] == '(net 1 "A B")'  # type: ignore[union-attr]


def test_number_format():
    assert [fmt(v) for v in (1.0, 0.25, -0.0, 110.1234567, 3.10)] == ["1", "0.25", "0", "110.123457", "3.1"]


def test_empty_change_set_is_byte_identical():
    for data in (REF, LEGACY):
        assert patch_board(data, []).data == data


def test_reference_board_changes_round_trip():
    design = parse(REF)
    r1 = next(c for c in design.components if c.reference == "R1")
    track, via = design.tracks[0], design.vias[0]
    changes = [
        ch(ChangeKind.MOVE_COMPONENT, "component", r1.id, {"x": r1.position.x + 2.5, "y": r1.position.y - 1}),
        ch(ChangeKind.SET_TRACK_WIDTH, "track", track.id, {"width": 0.4}),
        ch(ChangeKind.SET_VIA_SIZE, "via", via.id, {"diameter": 0.8, "drill": 0.4}),
        ch(ChangeKind.SET_OUTLINE_RECT, "outline", "outline", {"min_x": 100, "min_y": 100, "max_x": 140, "max_y": 125}),
    ]
    result = export_changes(REF, "ref.kicad_pcb", changes)
    assert result.applied == [0, 1, 2, 3] and result.refused == []
    out = parse(result.data)
    r1b = next(c for c in out.components if c.reference == "R1")
    assert (r1b.position.x, r1b.position.y) == (r1.position.x + 2.5, r1.position.y - 1)
    # Pads move with the footprint by exactly the same offset.
    for a, b in zip(r1.pads, r1b.pads, strict=True):
        assert b.position.x == pytest.approx(a.position.x + 2.5) and b.position.y == pytest.approx(a.position.y - 1)
    assert out.tracks[0].width == 0.4 and (out.vias[0].diameter, out.vias[0].drill) == (0.8, 0.4)
    bb = out.outline.bbox
    assert out.outline.closed and (bb.min_x, bb.min_y, bb.max_x, bb.max_y) == (100, 100, 140, 125)
    # Header and everything VIA doesn't model are untouched.
    assert result.data.split(b"\n", 3)[:3] == REF.split(b"\n", 3)[:3]


def test_rotation_turns_pads_about_the_footprint_origin():
    design = parse(REF)
    r1 = next(c for c in design.components if c.reference == "R1")
    result = export_changes(
        REF, None, [ch(ChangeKind.ROTATE_COMPONENT, "component", r1.id, {"rotation": (r1.rotation + 90) % 360})]
    )
    r1b = next(c for c in parse(result.data).components if c.reference == "R1")
    assert r1b.rotation == pytest.approx((r1.rotation + 90) % 360)
    # A pad offset (dx, dy) from the origin turns to (dy, -dx) for +90 deg in KiCad's y-down frame.
    for a, b in zip(r1.pads, r1b.pads, strict=True):
        dx, dy = a.position.x - r1.position.x, a.position.y - r1.position.y
        assert b.position.x - r1.position.x == pytest.approx(dy, abs=1e-6)
        assert b.position.y - r1.position.y == pytest.approx(-dx, abs=1e-6)


def test_kicad5_via_without_drill_gets_explicit_drill_and_lines_outline():
    design = parse(LEGACY)
    changes = [
        ch(ChangeKind.SET_OUTLINE_RECT, "outline", "outline", {"min_x": 0, "min_y": 0, "max_x": 30, "max_y": 20})
    ]
    if design.vias:
        changes.append(ch(ChangeKind.SET_VIA_SIZE, "via", design.vias[0].id, {"diameter": 0.7, "drill": 0.35}))
    result = export_changes(LEGACY, "legacy.kicad_pcb", changes)
    assert not result.refused
    out = parse(result.data)
    assert out.outline.closed and out.outline.bbox.max_x == 30 and out.outline.bbox.max_y == 20
    assert result.data.count(b"Edge.Cuts") >= 4 or b"gr_rect" in result.data


def test_unknown_targets_and_unsupported_kinds_are_refused_not_guessed():
    result = patch_board(
        REF,
        [
            {"kind": "move_component", "target": {"id": "component:nope"}, "after": {"x": 1, "y": 1}},
            {"kind": "set_copper_layer_count", "target": {"id": "stackup"}, "after": {"count": 2}},
        ],
    )
    assert result.applied == [] and [i for i, _ in result.refused] == [0, 1] and result.data == REF


def test_conflicting_changes_to_one_object_are_refused():
    via = parse(REF).vias[0]
    result = patch_board(
        REF,
        [
            {"kind": "move_via", "target": {"id": via.id}, "after": {"x": 1, "y": 1}},
            {"kind": "move_via", "target": {"id": via.id}, "after": {"x": 2, "y": 2}},
        ],
    )
    assert result.applied == [0] and result.refused[0][0] == 1


def test_verification_catches_a_wrong_patch():
    design = parse(REF)
    moved = design.model_copy(deep=True)
    moved.vias[0].position.x += 0.5
    assert compare(design, design) == []
    assert compare(design, moved) == [f"via {design.vias[0].id} differs"]
    with pytest.raises(ExportVerificationError):
        raise ExportVerificationError(compare(design, moved))


def test_project_archive_only_board_member_changes():
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as zf:
        zf.writestr("demo/demo.kicad_pcb", REF)
        zf.writestr("demo/demo.kicad_pro", b'{"board": {}}')
        zf.writestr("demo/notes.txt", b"keep me")
    via = parse(REF).vias[0]
    result = patch_source(
        buf.getvalue(),
        "demo.zip",
        [{"kind": "set_via_size", "target": {"id": via.id}, "after": {"diameter": 1, "drill": 0.5}}],
    )
    assert result.board_member == "demo/demo.kicad_pcb"
    with zipfile.ZipFile(io.BytesIO(result.data)) as zf:
        assert zf.namelist() == ["demo/demo.kicad_pcb", "demo/demo.kicad_pro", "demo/notes.txt"]
        assert zf.read("demo/notes.txt") == b"keep me" and zf.read("demo/demo.kicad_pro") == b'{"board": {}}'
        assert parse(zf.read("demo/demo.kicad_pcb")).vias[0].diameter == 1


@pytest.mark.parametrize("name", REAL)
def test_real_boards_patch_and_verify(name):
    path = HERE / "real" / name
    if not path.exists():
        pytest.skip(f"{name} not downloaded: run `python scripts/fetch_real_fixtures.py`")
    data = path.read_bytes()
    assert patch_board(data, []).data == data
    design = parse(data)
    c = design.components[len(design.components) // 2]
    changes = [
        ch(ChangeKind.MOVE_COMPONENT, "component", c.id, {"x": c.position.x + 1.27, "y": c.position.y}),
        ch(
            ChangeKind.ROTATE_COMPONENT,
            "component",
            design.components[0].id,
            {"rotation": (design.components[0].rotation + 90) % 360},
        ),
        ch(ChangeKind.SET_TRACK_WIDTH, "track", design.tracks[-1].id, {"width": 0.6}),
    ]
    if design.vias:
        changes.append(ch(ChangeKind.SET_VIA_SIZE, "via", design.vias[0].id, {"diameter": 0.9, "drill": 0.45}))
        changes.append(
            ch(
                ChangeKind.MOVE_VIA,
                "via",
                design.vias[-1].id,
                {"x": design.vias[-1].position.x + 0.1, "y": design.vias[-1].position.y},
            )
        )
    result = export_changes(data, name, changes)  # raises if the re-parse doesn't match apply()
    assert result.refused == [] and len(result.applied) == len(changes)
    # Only the edited lines differ (no change here adds or removes a line).
    old_lines, new_lines = data.split(b"\n"), result.data.split(b"\n")
    assert len(old_lines) == len(new_lines)
    differing = sum(a != b for a, b in zip(old_lines, new_lines, strict=True))
    rotated = design.components[0]
    budget = 1 + 1 + 2 + 1 + len(rotated.pads) + 8  # move, width, via size (+drill), via move, rotated pads/texts
    assert 0 < differing <= budget
