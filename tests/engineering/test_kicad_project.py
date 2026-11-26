"""KiCad project archives (.zip with .kicad_pcb + .kicad_pro + .kicad_dru).

Synthetic archives are built in the tests from the hand-authored reference board and
hand-written project files; expected values come from those files. Real KiCad 6-9 demo
projects (CC BY-SA, fetched on demand) check that KiCad 6's per-class net lists and
KiCad 7+'s net-class patterns resolve to the same classes.
"""

from __future__ import annotations

import io
import json
import re
import zipfile
from pathlib import Path

import pytest

from via_pcb import ArchiveLimits, ProjectArchiveError, parse_pcb, read_project

FIXTURES = Path(__file__).parent / "fixtures"
REAL = Path(__file__).parent / "real"
BOARD = (FIXTURES / "via_reference_v8.kicad_pcb").read_bytes()  # nets: VCC, SIG, GND

PRO = {
    "meta": {"filename": "ref.kicad_pro", "version": 1},
    "board": {
        "design_settings": {
            "rules": {
                "min_clearance": 0.15,
                "min_track_width": 0.18,
                "min_via_annular_width": 0.1,
                "min_copper_edge_clearance": 0.3,
                "allow_microvias": False,
                "min_resolved_spokes": 2,  # not modelled: ignored
                "min_hole_to_hole": "0.25",  # wrong type: ignored, never coerced
            }
        }
    },
    "net_settings": {
        "classes": [
            {"name": "Default", "clearance": 0.2, "track_width": 0.25, "via_diameter": 0.6, "via_drill": 0.3},
            {"name": "Power", "clearance": 0.3, "track_width": 0.5, "diff_pair_width": 0.2, "diff_pair_gap": 0.25},
        ],
        "netclass_patterns": [{"netclass": "Power", "pattern": "VC?"}, {"netclass": "Missing", "pattern": "*"}],
    },
}

DRU = b"""(version 1)
(rule "HV clearance"
	(constraint clearance (min 0.5mm))
	(condition "A.NetClass == 'Power'"))
(rule "fine pitch"
	(layer outer)
	(severity warning)
	(constraint track_width (min 6mil) (opt 8mil))
	(constraint hole_size (min 0.2)))
"""


def make_zip(files: dict[str, bytes | str], **zinfo) -> bytes:
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as zf:
        for name, data in files.items():
            zf.writestr(name, data)
    return buf.getvalue()


def project_zip(**extra: bytes | str) -> bytes:
    return make_zip({"ref/ref.kicad_pcb": BOARD, "ref/ref.kicad_pro": json.dumps(PRO), **extra})


def test_project_rules_and_net_classes():
    d = parse_pcb(project_zip(), filename="ref.zip")
    c = d.constraints
    assert c.rules_source == "project_file"
    r = c.rules
    assert (r.min_clearance, r.min_track_width, r.min_via_annular_width, r.min_copper_edge_clearance) == (
        0.15, 0.18, 0.1, 0.3,
    )  # fmt: skip
    assert r.allow_microvias is False
    assert r.min_hole_to_hole is None  # a string in the file: not coerced
    classes = {nc.name: nc for nc in c.net_classes}
    assert set(classes) == {"Default", "Power"}  # the pattern for unknown class "Missing" is dropped
    assert classes["Power"].patterns == ["VC?"]
    assert classes["Power"].nets == ["VCC"]  # "VC?" matches VCC only
    assert sorted(classes["Default"].nets) == ["GND", "SIG"]
    assert (classes["Power"].track_width, classes["Power"].diff_pair_gap, classes["Power"].via_drill) == (
        0.5,
        0.25,
        None,
    )


def test_source_identifies_the_archive_and_members():
    data = project_zip()
    d = parse_pcb(data, filename="ref.zip")
    import hashlib

    assert d.source.filename == "ref.zip"
    assert d.source.sha256 == hashlib.sha256(data).hexdigest()
    assert d.source.size_bytes == len(data)
    assert d.source.board_file == "ref/ref.kicad_pcb"
    assert d.source.project_files == ["ref/ref.kicad_pro"]
    assert d.stats.component_count == 4  # the board itself parsed as usual


def test_custom_rules_are_recorded_not_evaluated():
    d = parse_pcb(project_zip(**{"ref/ref.kicad_dru": DRU}), filename="ref.zip")
    hv, fine = d.constraints.custom_rules
    assert (hv.name, hv.condition, hv.layer, hv.severity) == ("HV clearance", "A.NetClass == 'Power'", None, None)
    assert (hv.constraints[0].kind, hv.constraints[0].min) == ("clearance", 0.5)
    assert (fine.layer, fine.severity) == ("outer", "warning")
    width, hole = fine.constraints
    assert (width.kind, width.min, width.opt, width.max) == ("track_width", 0.1524, 0.2032, None)  # 6 mil, 8 mil
    assert hole.min is None and hole.raw == "(constraint hole_size (min 0.2))"  # no unit stated: not guessed
    assert d.source.project_files == ["ref/ref.kicad_pro", "ref/ref.kicad_dru"]


def test_kicad6_style_class_net_lists_and_kicad8_assignments():
    pro = json.loads(json.dumps(PRO))
    pro["net_settings"]["netclass_patterns"] = []
    pro["net_settings"]["classes"][1]["nets"] = ["GND"]  # KiCad 6
    pro["net_settings"]["netclass_assignments"] = {"SIG": "Power"}  # KiCad 8
    d = parse_pcb(make_zip({"b.kicad_pcb": BOARD, "b.kicad_pro": json.dumps(pro)}), filename="b.zip")
    classes = {nc.name: nc for nc in d.constraints.net_classes}
    assert sorted(classes["Power"].nets) == ["GND", "SIG"]
    assert classes["Default"].nets == ["VCC"]


def test_board_without_project_file_is_labelled():
    d = parse_pcb(make_zip({"only.kicad_pcb": BOARD}), filename="only.zip")
    assert d.constraints.rules_source == "board_file" and d.constraints.rules is None
    assert "missing_project_file" in {w.code for w in d.warnings}


def test_legacy_kicad5_project_file_is_reported():
    d = parse_pcb(make_zip({"old.kicad_pcb": BOARD, "old.pro": "[general]\n"}), filename="old.zip")
    assert "legacy_project_file" in {w.code for w in d.warnings}
    assert d.constraints.rules_source == "board_file"


def test_invalid_project_json_is_ignored_with_a_warning():
    d = parse_pcb(make_zip({"x.kicad_pcb": BOARD, "x.kicad_pro": "{not json"}), filename="x.zip")
    assert "invalid_project_file" in {w.code for w in d.warnings}
    assert d.constraints.rules_source == "board_file"


def test_backups_hidden_files_and_macos_metadata_are_ignored():
    files = {
        "p/p.kicad_pcb": BOARD,
        "p/p.kicad_pro": json.dumps(PRO),
        "p/p-backups/p-2026-01-01.zip": b"PK\x03\x04nested",
        "__MACOSX/p/._p.kicad_pcb": b"junk",
        "p/.history/old.kicad_pcb": BOARD,
    }
    assert read_project(make_zip(files)).board_name == "p/p.kicad_pcb"


def test_several_boards_pick_the_one_with_a_project():
    files = {"a/a.kicad_pcb": BOARD, "b/b.kicad_pcb": BOARD, "b/b.kicad_pro": json.dumps(PRO)}
    assert read_project(make_zip(files)).board_name == "b/b.kicad_pcb"


@pytest.mark.parametrize(
    ("files", "message"),
    [
        ({"readme.txt": b"hi"}, "doesn't contain a .kicad_pcb"),
        ({"a.kicad_pcb": BOARD, "b.kicad_pcb": BOARD}, "several boards"),
        ({"../evil.kicad_pcb": BOARD}, "unsafe path"),
        ({"/abs/evil.kicad_pcb": BOARD}, "unsafe path"),
        ({"C:/evil.kicad_pcb": BOARD}, "unsafe path"),
        ({"bomb.kicad_pcb": b"\0" * (8 * 1024 * 1024)}, "compressed suspiciously well"),
    ],
    ids=["no-board", "ambiguous", "dotdot", "absolute", "drive-letter", "zip-bomb"],
)
def test_unsafe_or_unusable_archives_are_refused(files, message):
    with pytest.raises(ProjectArchiveError, match=message):
        read_project(make_zip(files))


def test_not_a_zip_is_refused():
    with pytest.raises(ProjectArchiveError, match=r"valid \.zip"):
        read_project(b"PK\x03\x04 truncated garbage")


def test_encrypted_members_are_refused():
    # zipfile can't write encrypted entries, so set the "encrypted" flag bit in the raw headers.
    raw = bytearray(make_zip({"x.kicad_pcb": BOARD}))
    local = raw.index(b"PK\x03\x04")
    central = raw.index(b"PK\x01\x02")
    raw[local + 6] |= 0x1
    raw[central + 8] |= 0x1
    with pytest.raises(ProjectArchiveError, match="Encrypted"):
        read_project(bytes(raw))


def test_entry_count_and_size_limits():
    many = {f"f{i}.txt": b"x" for i in range(20)} | {"b.kicad_pcb": BOARD}
    with pytest.raises(ProjectArchiveError, match="more than 10 entries"):
        read_project(make_zip(many), ArchiveLimits(max_entries=10))
    with pytest.raises(ProjectArchiveError, match="larger than"):
        read_project(make_zip({"b.kicad_pcb": BOARD}), ArchiveLimits(max_board_bytes=1024))
    with pytest.raises(ProjectArchiveError, match="larger than"):
        read_project(project_zip(), ArchiveLimits(max_side_file_bytes=10))


# --- Real KiCad demo projects ----------------------------------------------------------------

TAGS = ["6.0.11", "7.0.11", "8.0.8", "9.0.0"]


def real_project(project: str, tag: str) -> bytes:
    pcb, pro = REAL / f"{project}_{tag}.kicad_pcb", REAL / f"{project}_{tag}.kicad_pro"
    if not (pcb.exists() and pro.exists()):
        pytest.skip("real projects not fetched (scripts/fetch_real_fixtures.py)")
    return make_zip(
        {f"{project}/{project}.kicad_pcb": pcb.read_bytes(), f"{project}/{project}.kicad_pro": pro.read_bytes()}
    )


@pytest.mark.parametrize("project", ["video", "pic_programmer"])
def test_real_projects_resolve_the_same_classes_in_every_version(project):
    resolved = {}
    for tag in TAGS:
        d = parse_pcb(real_project(project, tag), filename=f"{project}.zip")
        c = d.constraints
        assert c.rules_source == "project_file" and c.rules is not None
        raw = json.loads((REAL / f"{project}_{tag}.kicad_pro").read_text())["board"]["design_settings"]["rules"]
        assert c.rules.min_clearance == raw["min_clearance"] and c.rules.min_track_width == raw["min_track_width"]
        nets = {n.name for n in d.nets}
        in_classes = {n for nc in c.net_classes for n in nc.nets}
        assert in_classes == nets  # every net lands in a class (Default when nothing else matches)
        resolved[tag] = {nc.name: sorted(nc.nets) for nc in c.net_classes if nc.name != "Default"}
        assert not [w for w in d.warnings if w.code.endswith("project_file")]
    # KiCad 6 lists nets per class; KiCad 7+ uses patterns. Both must resolve to the class's
    # intended nets that exist on that board. (The 8.0 demo re-imported BUS1, after which its
    # +12V net became "unconnected-(BUS1-+12V-PadA2)", so the boards really differ.)
    intended = {name: set(nets) for name, nets in resolved["6.0.11"].items()}  # KiCad 6: explicit lists
    for tag, classes in resolved.items():
        board_nets = set(re.findall(r'\(net \d+ "([^"]+)"\)', (REAL / f"{project}_{tag}.kicad_pcb").read_text()))
        assert classes == {name: sorted(nets & board_nets) for name, nets in intended.items()}, tag


def test_real_video_power_class():
    d = parse_pcb(real_project("video", "9.0.0"), filename="video.zip")
    pwr = next(nc for nc in d.constraints.net_classes if nc.name == "pwr")
    assert (pwr.track_width, pwr.clearance, pwr.via_diameter, pwr.via_drill) == (0.25, 0.2, 0.8, 0.4)
    # Patterns "+12V", "+3.3V", "+5F"; the board has nets +3.3V and +5F but no net named exactly +12V.
    assert pwr.patterns == ["+12V", "+3.3V", "+5F"] and sorted(pwr.nets) == ["+3.3V", "+5F"]
    assert "+12V" not in {n.name for n in d.nets}
