"""De-identification of project-derived contributions (hand-derived cases)."""

from __future__ import annotations

from via_api.services.learn_scrub import GENERIC_NETS, residual_identifiers, scrub_text

NETS = {"MOTOR_PHASE_A", "GND", "+5V", "SPI_MOSI"}
NAMES = {"Acme Drone Controller", "board"}


def test_design_specific_names_are_removed_and_generic_power_names_kept():
    text = "Route MOTOR_PHASE_A away from SPI_MOSI; keep GND and +5V solid. See Acme Drone Controller."
    out, report = scrub_text(text, nets=NETS, names=NAMES)
    assert out == "Route <net> away from <net>; keep GND and +5V solid. See <project>."
    assert report.nets == 2 and report.names == 1


def test_reference_designators_are_removed_even_if_not_in_this_design():
    out, report = scrub_text("Move C12 and R3 next to U1. Use 10uF and a 4K7 pull-up.", nets=set(), names=set())
    assert out == "Move <part> and <part> next to <part>. Use 10uF and a 4K7 pull-up."
    assert report.parts == 3


def test_anything_shaped_like_a_designator_goes_even_when_it_is_really_a_value():
    # "R100K" reads as R100 + a suffix letter. Over-removing is the safe direction.
    out, _ = scrub_text("A R100K divider", nets=set(), names=set())
    assert out == "A <part> divider"


def test_ids_and_file_names_are_removed():
    text = "Finding 3f2b8c1e-aaaa-bbbb-cccc-1234567890ab in motor_ctrl.kicad_pcb."
    out, report = scrub_text(text, nets=set(), names=set())
    assert out == "Finding <id> in <file>."
    assert report.ids == 1 and report.names == 1


def test_a_net_name_inside_a_longer_word_is_not_mangled():
    out, _ = scrub_text("The NETA1 and NET_A1X nets", nets={"NET_A1"}, names=set())
    assert out == "The NETA1 and NET_A1X nets"


def test_residual_check_finds_what_a_bad_scrub_would_leave():
    assert residual_identifiers("tie U7 to MOTOR_PHASE_A", refdes={"U7"}, nets=NETS, names=NAMES) == [
        "MOTOR_PHASE_A",
        "U7",
    ]
    assert residual_identifiers("tie <part> to <net> and GND", refdes={"U7"}, nets=NETS, names=NAMES) == []
    assert "GND" in GENERIC_NETS
