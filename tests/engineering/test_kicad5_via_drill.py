"""KiCad 5 omits a via's drill when it uses the net class default; VIA resolves it (no zero-fill).

Found by the Stage 2 manufacturing checks: 750 of 815 vias in the KiCad 5.1 `video` demo had drill 0.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from via_pcb import parse_pcb

FIXTURES = Path(__file__).parent / "fixtures"
REAL = Path(__file__).parent / "real"

BOARD = """(kicad_pcb (version 20171130) (host pcbnew 5.1.12)
  (general (thickness 1.6))
  (layers (0 F.Cu signal) (31 B.Cu signal) (44 Edge.Cuts user))
  (setup (via_size 0.8) (via_drill 0.35))
  (net 0 "") (net 1 GND) (net 2 VCC) (net 3 SIG)
  (net_class Default "Default" (clearance 0.2) (trace_width 0.25) (via_dia 0.8) (via_drill 0.4)
    (add_net GND) (add_net SIG))
  (net_class pwr "" (clearance 0.3) (trace_width 0.5) (via_dia 1.0) (via_drill 0.6) (add_net VCC))
  (via (at 10 10) (size 0.8) (layers F.Cu B.Cu) (net 1))
  (via (at 12 10) (size 1.0) (layers F.Cu B.Cu) (net 2))
  (via (at 14 10) (size 0.8) (drill 0.3) (layers F.Cu B.Cu) (net 3))
  (via (at 16 10) (size 0.8) (layers F.Cu B.Cu) (net 0))
)
"""


def test_default_drill_comes_from_the_net_class():
    d = parse_pcb(BOARD.encode(), filename="v5.kicad_pcb")
    assert [v.drill for v in d.vias] == [0.4, 0.6, 0.3, 0.4]  # GND→Default, VCC→pwr, explicit, no net→Default
    assert "via_default_drill" in {w.code for w in d.warnings}


def test_falls_back_to_the_board_default_without_net_classes():
    text = "\n".join(line for line in BOARD.splitlines() if "net_class" not in line and "add_net" not in line)
    d = parse_pcb(text.encode(), filename="v5.kicad_pcb")
    assert [v.drill for v in d.vias] == [0.35, 0.35, 0.3, 0.35]


@pytest.mark.skipif(not (REAL / "video_5.1.12.kicad_pcb").exists(), reason="real boards not fetched")
def test_kicad5_video_vias_match_kicad6():
    v5 = parse_pcb(REAL / "video_5.1.12.kicad_pcb")
    v6 = parse_pcb(REAL / "video_6.0.11.kicad_pcb")
    assert all(v.drill > 0 for v in v5.vias)
    assert {v.drill for v in v5.vias} == {v.drill for v in v6.vias} == {0.4}
