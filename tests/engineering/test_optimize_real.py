"""VIA Optimize on real KiCad boards (fetched by scripts/fetch_real_fixtures.py, never committed).

Invariants only, no expected numbers copied from output: the original is untouched, runs are
deterministic, and nothing that fails a hard constraint is ranked or passed.
"""

from __future__ import annotations

import copy
from pathlib import Path

import pytest
from via_opt import Constraints, Objective, ValidationStatus, optimize

from via_pcb import parse_pcb

REAL = Path(__file__).parent / "real"
BOARDS = [REAL / "video_9.0.0.kicad_pcb", REAL / "pic_programmer_9.0.0.kicad_pcb"]
OBJECTIVES = [Objective.AREA, Objective.PLACEMENT, Objective.MANUFACTURABILITY]


def load(path: Path):
    if not path.exists():
        pytest.skip(f"{path.name} not fetched (run scripts/fetch_real_fixtures.py)")
    return parse_pcb(path.read_bytes(), filename=path.name)


@pytest.mark.parametrize("path", BOARDS, ids=lambda p: p.name)
def test_original_is_never_modified_and_runs_are_deterministic(path):
    design = load(path)
    before = copy.deepcopy(design.model_dump())
    first = optimize(design, OBJECTIVES, Constraints())
    assert design.model_dump() == before
    second = optimize(load(path), OBJECTIVES, Constraints())
    assert [c.candidate_hash for c in first.candidates] == [c.candidate_hash for c in second.candidates]
    assert first.baseline == second.baseline


@pytest.mark.parametrize("path", BOARDS, ids=lambda p: p.name)
def test_failed_candidates_are_never_ranked(path):
    result = optimize(load(path), OBJECTIVES, Constraints(), weights={Objective.AREA: 1.0})
    for c in result.candidates:
        if c.validation.status == ValidationStatus.FAILED:
            assert c.score is None or c.score.value is None
