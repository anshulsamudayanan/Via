"""Validation against real KiCad-generated boards (KiCad demo projects, 5.1 → 9.0).

These files are CC BY-SA 4.0 and are not committed. Fetch them with
``python scripts/fetch_real_fixtures.py`` (CI does this automatically). Without
them, these tests are reported as skipped with that instruction.

Expected values are not taken from the parser. The tests check:
* counts against an independent regex scan of the raw text,
* invariants that must hold across KiCad versions of the same design,
* electrical consistency: routed copper must end on pads of the same net, which
  only holds if footprint-to-board transforms (rotation, pad angles) are right.
"""

from __future__ import annotations

import collections
import json
import math
import re
from pathlib import Path

import pytest

from via_pcb import PCBDesign, parse_pcb

HERE = Path(__file__).parent
MANIFEST = json.loads((HERE / "real_fixtures.json").read_text())
REAL = HERE / "real"
FIXTURES = list(MANIFEST["fixtures"])


def _load(fx: dict) -> tuple[PCBDesign, str]:
    path = REAL / fx["file"]
    if not path.exists():
        pytest.skip(f"{fx['file']} not downloaded: run `python scripts/fetch_real_fixtures.py`")
    return parse_pcb(path), path.read_text(encoding="utf-8")


_cache: dict[str, tuple[PCBDesign, str]] = {}


def load(fx: dict) -> tuple[PCBDesign, str]:
    if fx["file"] not in _cache:
        _cache[fx["file"]] = _load(fx)
    return _cache[fx["file"]]


def regex_count(text: str, pattern: str) -> int:
    return len(re.findall(pattern, text, flags=re.MULTILINE))


ids = [fx["file"] for fx in FIXTURES]


@pytest.mark.parametrize("fx", FIXTURES, ids=ids)
def test_counts_match_independent_text_scan(fx):
    design, text = load(fx)
    assert design.source.format_version == re.search(r"\(version (\d+)\)", text).group(1)
    assert design.stats.component_count == regex_count(text, r"^\s*\((?:footprint|module) ")
    assert sum(t.kind == "segment" for t in design.tracks) == regex_count(text, r"^\s*\(segment[\s(]")
    assert sum(t.kind == "arc" for t in design.tracks) == regex_count(text, r"^\s*\(arc \(start")
    assert design.stats.via_count == regex_count(text, r"^\s*\(via[\s(]")
    assert design.stats.zone_count == regex_count(text, r"^\s*\(zone[\s(]")
    # The board net table precedes the first footprint; pads repeat "(net n ...)" later.
    head = text[: re.search(r"^\s*\((?:footprint|module) ", text, flags=re.MULTILINE).start()]
    assert design.stats.net_count == regex_count(head, r"^\s*\(net [1-9]\d* ")
    assert design.outline.closed
    assert design.warnings == []


@pytest.mark.parametrize("project", sorted({fx["project"] for fx in FIXTURES}))
def test_design_is_stable_across_kicad_versions(project):
    """The same demo, re-saved by each KiCad release, must parse to the same board.

    The demos were genuinely edited between 5.1 and 7.0 (a few parts moved), so
    exact placement is compared only for the releases where the design is
    unchanged (7.0 → 8.0 → 9.0). The reference designators match in every version.
    """
    loaded = {fx["kicad_tag"]: load(fx)[0] for fx in FIXTURES if fx["project"] == project}
    latest = loaded["9.0.0"]
    refs = sorted(c.reference for c in latest.components)
    for design in loaded.values():
        assert sorted(c.reference for c in design.components) == refs
        assert design.stats.copper_layer_count == latest.stats.copper_layer_count
        assert design.stats.components_bottom == latest.stats.components_bottom

    base = {c.reference: c for c in loaded["7.0.11"].components}
    for tag in ("8.0.8", "9.0.0"):
        d = loaded[tag]
        assert (d.stats.board_width, d.stats.board_height) == pytest.approx(
            (loaded["7.0.11"].stats.board_width, loaded["7.0.11"].stats.board_height), abs=1e-3
        )
        differing = []
        for c in d.components:
            b = base[c.reference]
            assert (c.position.x, c.position.y, c.rotation) == pytest.approx(
                (b.position.x, b.position.y, b.rotation), abs=1e-3
            ), c.reference
            if _pad_positions(c) != _pad_positions(b):
                differing.append(c.reference)
        # KiCad's demos re-imported a few library footprints between releases (raw
        # local pad coordinates changed, e.g. POT1, P3, BUS1). Placement is identical;
        # at most 2% of footprints may differ, and they're listed if more do.
        assert len(differing) <= 0.02 * len(d.components), (tag, differing)


def _pad_positions(comp) -> set[tuple[str, float, float]]:
    return {(p.number, round(p.position.x, 3), round(p.position.y, 3)) for p in comp.pads}


@pytest.mark.parametrize("fx", FIXTURES, ids=ids)
def test_routed_tracks_end_on_pads_of_the_same_net(fx):
    design, _ = load(fx)
    ends: dict[str | None, list[tuple[float, float]]] = collections.defaultdict(list)
    for t in design.tracks:
        ends[t.net] += [(t.start.x, t.start.y), (t.end.x, t.end.y)]
    zone_nets = {z.net for z in design.zones}
    checked = matched = 0
    for c in design.components:
        for p in c.pads:
            # Pads on zone nets may legitimately connect through the copper pour only.
            if not p.net or p.net not in ends or p.net in zone_nets:
                continue
            checked += 1
            r = max(p.size.x, p.size.y) / 2
            if any(math.hypot(x - p.position.x, y - p.position.y) <= r for x, y in ends[p.net]):
                matched += 1
    assert checked > 50
    assert matched / checked >= 0.99, f"{matched}/{checked} routed pads have a track ending on them"


def test_pad_angles_are_absolute_and_missing_means_zero():
    """KiCad 6 video board: a TQFP-100 rotated -90° whose side pads have local +90°.

    KiCad writes the absolute angle (-90 + 90 = 0) and omits it when zero, so
    those pads must come out at 0°, not at the footprint's angle. Angles are
    normalized to [0, 360), so -90° is reported as 270°.
    """
    fx = next(f for f in FIXTURES if f["file"] == "video_6.0.11.kicad_pcb")
    design, _ = load(fx)
    qfps = [c for c in design.components if c.footprint.endswith("TQFP-100_14x14mm_P0.5mm") and c.rotation == 270]
    assert qfps
    angles = collections.Counter(p.rotation for p in qfps[0].pads)
    assert angles == {270.0: 50, 0.0: 50}
