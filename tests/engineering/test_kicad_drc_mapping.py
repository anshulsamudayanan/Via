"""Mapping a real KiCad 9 DRC report onto VIA findings.

`fixtures/via_reference_v8.kicad_drc.json` is KiCad 9.0.6's actual report for our hand-authored
reference board (which genuinely has shorts and clearance errors).
"""

from __future__ import annotations

import json
from collections import Counter
from pathlib import Path

import pytest

from via_pcb import parse_pcb
from via_pcb.analysis import CheckStatus, Severity, Source, Verification, default_engine

FIXTURES = Path(__file__).parent / "fixtures"
REPORT = json.loads((FIXTURES / "via_reference_v8.kicad_drc.json").read_text())


@pytest.fixture(scope="module")
def design():
    return parse_pcb(FIXTURES / "via_reference_v8.kicad_pcb")


def run(design, rules="defaults", report=REPORT):
    drc = {"report": report, "rules": rules, "kicad_version": "9.0.6", "duration_seconds": 1.2}
    return default_engine().run(design, options={"kicad_drc": drc}, only={"kicad_drc"})


def test_every_violation_becomes_a_finding_except_environment_checks(design):
    result = run(design)
    (check,) = result.checks
    assert check.status == CheckStatus.OK
    assert Counter(f.rule for f in result.findings) == {
        "clearance": 6, "solder_mask_bridge": 4, "hole_clearance": 3, "shorting_items": 2,
    }  # fmt: skip
    assert check.details["suppressed_environment_checks"] == 4  # lib_footprint_issues
    assert check.details["kicad_version"] == "9.0.6" and check.details["kicad_violations"] == 19
    assert all(f.source == Source.KICAD_DRC for f in result.findings)


def test_shorts_are_critical_and_mapped_to_exact_objects(design):
    shorts = [f for f in run(design).findings if f.rule == "shorting_items"]
    assert {f.severity for f in shorts} == {Severity.CRITICAL}
    c1 = next(c for c in design.components if c.reference == "C1")
    pad2 = next(p for p in c1.pads if p.number == "2")
    arc = next(t for t in design.tracks if t.uuid == "a1f0b6a4-0000-4000-8000-0000000000c6")
    seg = next(t for t in design.tracks if t.uuid == "a1f0b6a4-0000-4000-8000-0000000000c7")
    ids = sorted(tuple(sorted(o.id for o in f.objects)) for f in shorts)
    assert ids == sorted([tuple(sorted((pad2.id, arc.id))), tuple(sorted((pad2.id, seg.id)))])
    for f in shorts:
        assert f.components == ["C1"] and f.nets == ["GND", "SIG"]
        assert (120.0, 114.225) in {(p.x, p.y) for p in f.region.points}
        assert "Items shorting two nets" in f.evidence[0].value
    assert len({f.fingerprint for f in shorts}) == 2
    assert {o.label for f in shorts for o in f.objects if o.kind == "track"} == {
        "Arc track on B.Cu [SIG], 3.14 mm", "Track on B.Cu [SIG], 1.77 mm",
    }  # fmt: skip


def test_default_rules_are_heuristic_and_say_so(design):
    f = run(design, rules="defaults").findings[0]
    assert f.verification == Verification.HEURISTIC and f.confidence == 0.6
    assert "default rules" in f.explanation
    assert {e.label: e.value for e in f.evidence}["Rules"] == "KiCad default rules (no .kicad_pro)"


def test_project_rules_are_verified(design):
    f = run(design, rules="project_file").findings[0]
    assert f.verification == Verification.VERIFIED and f.confidence == 1.0
    assert "default rules" not in f.explanation


def test_fingerprints_are_stable_and_unique(design):
    a, b = run(design).findings, run(design).findings
    assert [f.fingerprint for f in a] == [f.fingerprint for f in b]
    assert len({f.fingerprint for f in a}) == len(a)


def test_pads_without_uuids_are_mapped_by_reference(design):
    """KiCad 5-7 files have no pad UUIDs; KiCad then reports random ones, so VIA maps by 'Pad N of REF'."""
    report = json.loads(json.dumps(REPORT))
    for v in report["violations"]:
        for item in v["items"]:
            item["uuid"] = "ffffffff-ffff-4fff-8fff-ffffffffffff"  # unknown to VIA
    shorts = [f for f in run(design, report=report).findings if f.rule == "shorting_items"]
    c1 = next(c for c in design.components if c.reference == "C1")
    pad2 = next(p for p in c1.pads if p.number == "2")
    for f in shorts:
        assert [o.id for o in f.objects] == [pad2.id]  # the track can't be identified: kept as evidence
        assert any("Track" in e.value for e in f.evidence if e.label == "Item")


@pytest.mark.parametrize(
    ("drc", "reason"),
    [
        (None, "wasn't run"),
        ({"error": "The KiCad service couldn't be reached."}, "couldn't run: The KiCad service couldn't be reached."),
        ({"rules": "defaults"}, "no report"),
    ],
)
def test_skipped_with_the_reason(design, drc, reason):
    options = {} if drc is None else {"kicad_drc": drc}
    (check,) = default_engine().run(design, options=options, only={"kicad_drc"}).checks
    assert check.status == CheckStatus.SKIPPED and reason in check.message


def test_clean_report_gives_no_findings(design):
    clean = {**REPORT, "violations": [v for v in REPORT["violations"] if v["type"].startswith("lib_")]}
    assert run(design, report=clean).findings == []
