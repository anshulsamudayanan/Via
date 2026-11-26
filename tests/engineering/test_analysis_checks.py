"""Starter analysis checks on hand-authored fixtures (expected values derived by hand)."""

from __future__ import annotations

import io
import json
import zipfile
from pathlib import Path

from via_pcb import parse_pcb
from via_pcb.analysis import Severity, Source, Verification, default_engine

FIXTURES = Path(__file__).parent / "fixtures"
REF_TEXT = (FIXTURES / "via_reference_v8.kicad_pcb").read_text()


def findings(design, check_id):
    return [f for f in default_engine().run(design, only={check_id}).findings]


def edit(text: str, old: str, new: str) -> bytes:
    assert text.count(old) == 1, old
    return text.replace(old, new).encode()


# --- board_outline -----------------------------------------------------------------------------
# The reference outline is four lines: (100,100)-(150,100), (150,100)-(150,130), (100,130)-(150,130),
# (100,130)-(100,100). Removing the right-hand line leaves (150,100) and (150,130) unjoined.

RIGHT_EDGE = """	(gr_line
		(start 150 100)
		(end 150 130)
		(stroke (width 0.05) (type default))
		(layer "Edge.Cuts")
		(uuid "a1f0b6a4-0000-4000-8000-0000000000a2")
	)
"""


def test_closed_outline_has_no_finding():
    assert findings(parse_pcb(FIXTURES / "via_reference_v8.kicad_pcb"), "board_outline") == []


def test_open_outline_marks_the_unjoined_endpoints():
    d = parse_pcb(edit(REF_TEXT, RIGHT_EDGE, ""), filename="open.kicad_pcb")
    (f,) = findings(d, "board_outline")
    assert (f.rule, f.severity, f.source, f.verification) == (
        "outline_open",
        Severity.HIGH,
        Source.VIA_DETERMINISTIC,
        Verification.VERIFIED,
    )
    assert sorted((p.x, p.y) for p in f.region.points) == [(150.0, 100.0), (150.0, 130.0)]
    measured = {e.label: e for e in f.evidence}
    assert measured["Edge.Cuts graphics"].numeric_value == 3
    assert (
        measured["Unjoined outline endpoints"].numeric_value == 2
        and measured["Unjoined outline endpoints"].expected == "0"
    )
    assert "Parser" in measured  # the parser's own open_outline warning is quoted


def test_missing_outline():
    without = REF_TEXT
    for uuid in ("a1", "a2", "a3", "a4"):
        start = without.index(f'(uuid "a1f0b6a4-0000-4000-8000-0000000000{uuid}")')
        block_start = without.rindex("\t(gr_line", 0, start)
        block_end = without.index("\t)\n", start) + 3
        without = without[:block_start] + without[block_end:]
    (f,) = findings(parse_pcb(without.encode(), filename="none.kicad_pcb"), "board_outline")
    assert f.rule == "outline_missing" and f.severity == Severity.HIGH
    assert f.evidence[0].numeric_value == 0


def test_outline_fingerprint_is_stable_across_revisions():
    a = findings(parse_pcb(edit(REF_TEXT, RIGHT_EDGE, ""), filename="a.kicad_pcb"), "board_outline")[0]
    b_text = REF_TEXT.replace(RIGHT_EDGE, "").replace('(gr_text "VIA REF A"', '(gr_text "VIA REF B"')
    b = findings(parse_pcb(b_text.encode(), filename="b.kicad_pcb"), "board_outline")[0]
    assert a.fingerprint == b.fingerprint


# --- design_rules_source ---------------------------------------------------------------------


def test_kicad8_board_without_project_gets_an_info_finding():
    (f,) = findings(parse_pcb(FIXTURES / "via_reference_v8.kicad_pcb"), "design_rules_source")
    assert (f.rule, f.severity) == ("project_rules_missing", Severity.INFO)
    assert {e.label: e.value for e in f.evidence}["KiCad file version"] == "20240108"


def test_kicad5_board_keeps_rules_in_the_board_file():
    assert findings(parse_pcb(FIXTURES / "via_legacy_v5.kicad_pcb"), "design_rules_source") == []


def test_project_archive_satisfies_the_check():
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as zf:
        zf.writestr("r.kicad_pcb", REF_TEXT)
        zf.writestr("r.kicad_pro", json.dumps({"board": {"design_settings": {"rules": {"min_clearance": 0.2}}}}))
    assert findings(parse_pcb(buf.getvalue(), filename="r.zip"), "design_rules_source") == []


# --- import_warnings ---------------------------------------------------------------------------


def test_skipped_data_is_a_low_finding():
    (f,) = findings(parse_pcb(FIXTURES / "via_legacy_v5.kicad_pcb"), "import_warnings")
    assert (f.rule, f.severity) == ("unsupported_curve", Severity.LOW)
    assert "F.SilkS" in f.description


def test_notes_are_info_and_outline_warnings_are_left_to_the_outline_check():
    notes = findings(parse_pcb(FIXTURES / "via_features_v9.kicad_pcb"), "import_warnings")
    assert [(f.rule, f.severity) for f in notes] == [("stackup_sublayers", Severity.INFO)]
    open_board = parse_pcb(edit(REF_TEXT, RIGHT_EDGE, ""), filename="open.kicad_pcb")
    assert "open_outline" in {w.code for w in open_board.warnings}
    assert findings(open_board, "import_warnings") == []


# --- pads_without_net ----------------------------------------------------------------------------
# R1 pad 2 is on net GND in the reference board; removing its net leaves exactly that pad unassigned.


def test_copper_pad_without_net():
    clean = parse_pcb(FIXTURES / "via_reference_v8.kicad_pcb")
    assert findings(clean, "pads_without_net") == []
    r1 = next(c for c in clean.components if c.reference == "R1")
    pad2 = next(p for p in r1.pads if p.number == "2")
    assert pad2.net is not None
    text = REF_TEXT
    start = text.index('(pad "2"', text.index('(property "Reference" "R1"'))
    end = text.index("(uuid", start)
    block = text[start:end]
    net_token = block[block.index("(net ") : block.index(")", block.index("(net ")) + 1]
    d = parse_pcb((text[:start] + block.replace(net_token, "") + text[end:]).encode(), filename="nonet.kicad_pcb")
    (f,) = findings(d, "pads_without_net")
    assert f.components == ["R1"] and f.severity == Severity.LOW
    assert [o.label for o in f.objects] == ["R1", "R1 pad 2"]
    assert f.objects[1].id == pad2.id
    assert [(p.x, p.y) for p in f.region.points] == [(pad2.position.x, pad2.position.y)]
