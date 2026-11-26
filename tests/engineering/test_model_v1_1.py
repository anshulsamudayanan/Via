"""Schema 1.1 additions: object ids, locked flags, stackup, keep-out rules, pad and zone details.

Expected values come from reading `fixtures/via_features_v9.kicad_pcb` by hand (see its
entry in fixtures/README.md), not from parser output.
"""

from __future__ import annotations

import json
import re
from pathlib import Path

import pytest

from via_pcb import PCBDesign, parse_pcb

FIXTURES = Path(__file__).parent / "fixtures"
REAL = Path(__file__).parent / "real"
U = "f0000000-0000-4000-8000-"


@pytest.fixture(scope="module")
def design() -> PCBDesign:
    return parse_pcb(FIXTURES / "via_features_v9.kicad_pcb")


def test_schema_version(design):
    assert design.schema_version == "1.1.0"


def test_locked_footprints_both_syntaxes(design):
    by_ref = {c.reference: c for c in design.components}
    assert by_ref["J1"].locked is True  # KiCad 8+: (locked yes)
    assert by_ref["R1"].locked is True  # KiCad <= 7: bare `locked` token
    assert by_ref["J1"].id == by_ref["J1"].uuid == U + "000000000001"
    assert by_ref["R1"].uuid == U + "000000000002"  # (tstamp ...) is the uuid in older files


def test_locked_tracks_both_syntaxes(design):
    assert [t.locked for t in design.tracks] == [True, True, False, False]


def test_track_and_via_ids(design):
    t1, t2, t3, t4 = design.tracks
    assert t1.id == t1.uuid == U + "000000000101"
    assert t2.id == U + "000000000102"
    # Two identical tracks without uuid: content-derived id, the second disambiguated.
    assert t3.uuid is None and t3.id.startswith("trk:") and t4.id == t3.id + "~2"
    # The via reuses track 1's uuid (copy-paste in KiCad can do this): keeps the uuid, gets a derived id.
    (via,) = design.vias
    assert via.uuid == U + "000000000101"
    assert via.id.startswith("via:")


def test_all_ids_unique_and_stable_across_parses(design):
    again = parse_pcb(FIXTURES / "via_features_v9.kicad_pcb")

    def ids(d):
        return (
            [c.id for c in d.components]
            + [p.id for c in d.components for p in c.pads]
            + [t.id for t in d.tracks]
            + [v.id for v in d.vias]
            + [z.id for z in d.zones]
        )

    assert len(set(ids(design))) == len(ids(design)) == 2 + 3 + 4 + 1 + 2
    assert ids(design) == ids(again)
    assert None not in ids(design)


def test_pad_details(design):
    j1 = next(c for c in design.components if c.reference == "J1")
    p1, p2 = j1.pads
    assert p1.id == p1.uuid == U + "000000000011"
    assert p1.roundrect_ratio == 0.25
    assert p1.clearance == 0.3
    assert p1.solder_mask_margin == 0.05
    assert p1.solder_paste_margin == -0.02
    assert p1.solder_paste_ratio == -0.1
    assert p1.zone_connection == "solid"  # (zone_connect 2)
    # Pad 2 states none of these: None, never zero.
    assert p2.uuid is None and p2.id == f"{j1.id}/pad:2"
    assert (p2.roundrect_ratio, p2.clearance, p2.solder_mask_margin, p2.zone_connection) == (None, None, None, None)


def test_stackup(design):
    st = design.stackup
    assert st is not None
    assert [layer.name for layer in st.layers] == [
        "F.Mask", "F.Cu", "dielectric 1", "In1.Cu", "dielectric 2", "In2.Cu", "dielectric 3", "B.Cu", "B.Mask",
    ]  # fmt: skip
    core = st.layers[4]
    # Only the first sub-layer of "dielectric 2" is recorded, with a warning.
    assert (core.type, core.thickness, core.material, core.epsilon_r, core.loss_tangent) == (
        "core", 0.9, "FR4", 4.6, 0.018,
    )  # fmt: skip
    assert st.layers[1].thickness == 0.035 and st.layers[1].material is None
    assert st.copper_finish == "ENIG"
    assert st.dielectric_constraints is False
    assert "stackup_sublayers" in {w.code for w in design.warnings}


def test_zones(design):
    gnd, keepout = design.zones
    assert (gnd.priority, gnd.clearance, gnd.min_thickness, gnd.keepout, gnd.keepout_rules) == (
        2,
        0.3,
        0.2,
        False,
        None,
    )
    assert keepout.keepout and keepout.name == "antenna keep-out"
    r = keepout.keepout_rules
    assert (r.tracks, r.vias, r.pads, r.copper_pour, r.footprints) == (False, False, True, False, True)
    assert keepout.priority is None  # not stated


def test_no_stackup_means_none():
    assert parse_pcb(FIXTURES / "via_reference_v8.kicad_pcb").stackup is None


def test_schema_1_0_designs_still_load(design):
    """Designs persisted with schema 1.0.0 (before these fields existed) must still validate."""
    data = json.loads(design.model_dump_json())
    data["schema_version"] = "1.0.0"
    data.pop("stackup")
    new_fields = {"id", "locked", "roundrect_ratio", "clearance", "solder_mask_margin", "solder_paste_margin",
                  "solder_paste_ratio", "zone_connection", "keepout_rules", "priority", "min_thickness"}  # fmt: skip

    def strip(obj):
        if isinstance(obj, dict):
            return {k: strip(v) for k, v in obj.items() if k not in new_fields}
        if isinstance(obj, list):
            return [strip(v) for v in obj]
        return obj

    data = strip(data)
    for track in data["tracks"]:
        track.pop("uuid")
    old = PCBDesign.model_validate(data)
    assert old.schema_version == "1.0.0"
    assert old.tracks[0].id is None and old.stackup is None and old.components[0].locked is False


# --- Real boards (CC BY-SA, fetched on demand) -----------------------------------------------

REAL_BOARDS = sorted(REAL.glob("*.kicad_pcb")) if REAL.exists() else []


@pytest.mark.skipif(not REAL_BOARDS, reason="real boards not fetched (scripts/fetch_real_fixtures.py)")
@pytest.mark.parametrize("path", REAL_BOARDS, ids=lambda p: p.stem)
def test_real_boards_ids_locked_and_stackup(path):
    text = path.read_text()
    d = parse_pcb(path)
    ids = [c.id for c in d.components] + [p.id for c in d.components for p in c.pads]
    ids += [t.id for t in d.tracks] + [v.id for v in d.vias] + [z.id for z in d.zones]
    assert None not in ids and len(set(ids)) == len(ids)
    # Independent count of locked footprints: `(footprint "x" locked` (6-7) or `(locked yes)` directly
    # inside a footprint (8+; only footprints are locked in these demos).
    locked_raw = len(re.findall(r'\((?:footprint|module) "?[^\s"]+"? locked', text)) + text.count("(locked yes)")
    assert sum(c.locked for c in d.components) == locked_raw
    if "(stackup" in text:
        block = text[text.index("(stackup") :]
        block = block[: block.index("(copper_finish") if "(copper_finish" in block else len(block)]
        assert d.stackup is not None and len(d.stackup.layers) == len(re.findall(r'\(layer "', block))
    else:
        assert d.stackup is None
    # KiCad 8+ files give every pad a uuid, so every id is a source uuid.
    if int(d.source.format_version or 0) >= 20240108:
        assert all(p.id == p.uuid for c in d.components for p in c.pads)
