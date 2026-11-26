# ruff: noqa: E501  (test data)
"""AI orchestration with a scripted provider: grounding verification rejects invented data."""

from __future__ import annotations

import uuid

import pytest

from via_ai import AIRefusedError, ContextFinding, ContextFocus, ProjectContext, explain, review
from via_ai.context import ContextComponent, ContextLayer, ContextPurpose
from via_ai.evaluation import Case, evaluate
from via_ai.prompts import PROMPT_VERSION
from via_ai.providers.scripted import ScriptedProvider
from via_ai.routing import Task
from via_ai.schemas import Explanation


def context(**extra) -> ProjectContext:
    return ProjectContext(
        purpose=ContextPurpose.EXPLAIN,
        project_id=uuid.uuid4(), design_id=uuid.uuid4(), revision_id=uuid.uuid4(),
        revision_number=1, design_name="ref", source_format="kicad",
        stats={"component_count": 2, "board_width": 50.0},
        layers=[ContextLayer(name="F.Cu", kind="copper", side="top")],
        net_names=["GND", "SIG"],
        components=[ContextComponent(reference="C1", value="100n", footprint="C_0603", side="bottom"),
                    ContextComponent(reference="R1", value="10k", footprint="R_0603", side="top")],
        warnings=[],
        findings=[ContextFinding(id="f-1", check_id="kicad_drc", rule="shorting_items", severity="critical",
                                 source="kicad_drc", verification="verified", title="Items short two nets",
                                 description="Items shorting two nets (nets GND and SIG)", components=["C1"],
                                 nets=["GND", "SIG"], evidence=["Smallest gap: 0 mm", "Clearance: 0.2 mm"])],
        **extra,
    )  # fmt: skip


GOOD = Explanation(
    answer="C1 pad 2 (GND) touches a SIG track on B.Cu, which KiCad reports as a short.",
    key_points=["The short is between GND and SIG."],
    references=[{"kind": "component", "id": "C1"}, {"kind": "net", "id": "GND"}, {"kind": "finding", "id": "f-1"}],
    numbers_used=[{"value": 0.2, "unit": "mm", "source": "finding f-1: Clearance"}],
)


def test_grounded_answer_is_accepted_and_the_request_carries_the_context():
    provider = ScriptedProvider([GOOD])
    result = explain(provider, context(focus=ContextFocus(kind="finding", id="f-1")), "Why is this a short?")
    assert result.accepted and result.prompt_version == PROMPT_VERSION and len(result.context_sha256) == 64
    (request,) = provider.requests
    assert request.task == Task.EXPLAIN and "Never invent" in request.system
    assert '"f-1"' in request.messages[0].content and "finding f-1" in request.messages[0].content


@pytest.mark.parametrize(
    ("change", "problem"),
    [
        ({"references": [{"kind": "component", "id": "U7"}]}, "Reference not in the design: component:U7"),
        ({"references": [{"kind": "finding", "id": "f-999"}]}, "finding:f-999"),
        ({"answer": "Move U3 closer to C1."}, "Mentioned part not in the design: U3"),
        (
            {"numbers_used": [{"value": 0.127, "unit": "mm", "source": "made up"}]},
            "Number not found in the design data: 0.127 mm",
        ),
    ],
)
def test_invented_objects_and_numbers_are_rejected(change, problem):
    bad = Explanation.model_validate({**GOOD.model_dump(), **change})
    result = explain(ScriptedProvider([bad]), context(), "?")
    assert not result.accepted
    assert any(problem in p for p in result.report.problems)


def test_design_review_separates_findings_from_hypotheses():
    out = {
        "summary": "One verified short.",
        "sections": [{"area": "design_rules", "verified_findings": ["f-1"],
                      "hypotheses": [{"statement": "R1 may be unused", "rationale": "Only one net", "confidence": "low",
                                      "references": [{"kind": "component", "id": "R1"}], "validation": "Check the schematic"}]}],
        "recommendations": [{"problem": "Short between GND and SIG at C1", "proposed_change": "Reroute the SIG arc around C1 pad 2",
                             "rationale": "Removes the short", "evidence_finding_ids": ["f-1"], "confidence": "high",
                             "uncertainty": "Routing space near C1 is unknown", "references": [{"kind": "component", "id": "C1"}]}],
    }  # fmt: skip
    result = review(ScriptedProvider([out]), context())
    assert result.accepted and result.value.recommendations[0].evidence_finding_ids == ["f-1"]
    hallucinated = {**out, "sections": [{"area": "routing", "verified_findings": ["f-2"], "hypotheses": []}]}
    assert not review(ScriptedProvider([hallucinated]), context()).accepted


def test_refusals_propagate_and_are_never_replaced():
    with pytest.raises(AIRefusedError):
        explain(ScriptedProvider([AIRefusedError("declined")]), context(), "?")


def test_evaluation_harness_reports_grounding():
    bad = Explanation.model_validate({**GOOD.model_dump(), "references": [{"kind": "net", "id": "VBUS"}]})
    report = evaluate(
        ScriptedProvider([GOOD, bad, AIRefusedError("no")]),
        [Case("good", context(), "q"), Case("hallucinated", context(), "q"), Case("refused", context(), "q")],
    )
    assert (report.total, report.accepted, report.rejected, report.errors) == (3, 1, 1, 1)
    assert report.acceptance_rate == pytest.approx(1 / 3)
    assert "net:VBUS" in report.problems["hallucinated"][0]
