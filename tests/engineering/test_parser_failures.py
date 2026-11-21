"""The engine must reject bad input with a clear error, never crash or guess."""

import pytest

from via_pcb import AdapterNotFoundError, UnsupportedFormatError, parse_pcb
from via_pcb.adapters import KiCadAdapter, get_registry

MINIMAL = b'(kicad_pcb (version 20240108) (generator "pcbnew") (layers (0 "F.Cu" signal) (31 "B.Cu" signal)))'


def test_unknown_format_is_rejected_with_supported_list():
    with pytest.raises(AdapterNotFoundError, match=r"\.kicad_pcb"):
        parse_pcb(b"PK\x03\x04 not a board", filename="board.zip")


def test_wrong_extension_is_rejected():
    with pytest.raises(AdapterNotFoundError):
        parse_pcb(MINIMAL, filename="board.txt")


def test_kicad_schematic_is_not_a_board():
    with pytest.raises(AdapterNotFoundError):
        parse_pcb(b"(kicad_sch (version 20231120))", filename="x.kicad_pcb")


@pytest.mark.parametrize(
    "data, match",
    [
        (b'(kicad_pcb (version 20240108) (net 1 "GND"', "Malformed"),
        (b"(kicad_pcb (version 1)) trailing (junk)", "Malformed"),
        (b"(kicad_pcb (version 1) \xff\xfe)", "UTF-8"),
    ],
)
def test_malformed_kicad_files_raise_unsupported_format(data, match):
    with pytest.raises(UnsupportedFormatError, match=match):
        parse_pcb(data, filename="broken.kicad_pcb")


def test_adapter_rejects_non_kicad_bytes_directly():
    with pytest.raises(UnsupportedFormatError):
        KiCadAdapter().parse(b"hello")


def test_empty_board_parses_with_warnings():
    design = parse_pcb(MINIMAL, filename="empty.kicad_pcb")
    assert design.stats.component_count == 0
    assert design.outline.closed is False
    assert design.bbox is None
    assert [w.code for w in design.warnings] == ["missing_outline"]


def test_bom_and_leading_whitespace_are_accepted():
    design = parse_pcb(b"\xef\xbb\xbf\n  " + MINIMAL, filename="bom.kicad_pcb")
    assert design.source.format_version == "20240108"


def test_open_outline_and_unknown_net_warn():
    data = (
        b'(kicad_pcb (version 20240108) (layers (0 "F.Cu" signal) (44 "Edge.Cuts" user))'
        b' (net 0 "") (net 1 "A")'
        b' (gr_line (start 0 0) (end 10 0) (layer "Edge.Cuts") (stroke (width 0.1)))'
        b' (gr_line (start 10 0) (end 10 10) (layer "Edge.Cuts") (stroke (width 0.1)))'
        b' (segment (start 0 0) (end 1 0) (width 0.2) (layer "F.Cu") (net 7)))'
    )
    design = parse_pcb(data, filename="open.kicad_pcb")
    codes = {w.code for w in design.warnings}
    assert {"open_outline", "unknown_net"} <= codes
    assert design.stats.board_area is None
    assert design.tracks[0].net is None


def test_newer_file_version_warns_but_parses():
    data = MINIMAL.replace(b"20240108", b"20990101")
    design = parse_pcb(data, filename="future.kicad_pcb")
    assert "new_version" in {w.code for w in design.warnings}


def test_repeated_warnings_are_capped():
    segs = b"".join(b'(segment (start 0 0) (end 1 0) (width 0.2) (layer "F.Cu") (net 9))' for _ in range(50))
    design = parse_pcb(MINIMAL[:-1] + segs + b")", filename="many.kicad_pcb")
    unknown = [w for w in design.warnings if w.code == "unknown_net"]
    assert len(unknown) == 6  # 5 detailed + 1 summary
    assert "45 more" in unknown[-1].message


def test_registry_lists_kicad():
    assert ".kicad_pcb" in get_registry().extensions
