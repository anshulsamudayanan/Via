# ruff: noqa: E501  (test data)
"""AI orchestration with a scripted provider: grounding verification rejects invented data."""

from __future__ import annotations

import contextlib
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


def test_numbers_inside_identifiers_do_not_ground_an_answer():
    """Regression: a UUID containing "127e-3" once let an invented 0.127 mm pass (flaky in CI)."""
    from via_ai.verification import context_numbers

    ctx = context().model_copy(update={"design_id": uuid.UUID("0000127e-3abc-4000-8000-000000000000")})
    assert all(abs(n - 0.127) > 1e-9 for n in context_numbers(ctx))


def test_a_big_context_is_trimmed_to_the_input_budget_and_the_trim_is_recorded():
    from via_ai.orchestration import fit_context
    from via_ai.prompts import review_messages

    big = context().model_copy(
        update={
            "net_names": [f"NET{i}" for i in range(3000)],
            "components": [
                ContextComponent(reference=f"R{i}", value="10k", footprint="R_0603", side="top") for i in range(800)
            ],
        }
    )
    provider = ScriptedProvider([])
    provider.input_token_budget = 3000
    fitted = fit_context(provider, big, lambda c: sum(map(len, review_messages(c))))
    assert sum(map(len, review_messages(fitted))) // 3 <= 3000
    assert fitted.truncated["net_names"] > 0 and fitted.truncated["components"] > 0
    assert fitted.findings == big.findings  # the findings are what the review is about: kept while room remains


def test_a_context_that_cannot_fit_even_when_emptied_is_refused_not_sent():
    from via_ai import AIError
    from via_ai.orchestration import fit_context

    provider = ScriptedProvider([])
    provider.input_token_budget = 10
    with pytest.raises(AIError, match="too large"):
        fit_context(provider, context(), lambda c: 100000)


def test_no_budget_means_the_context_is_untouched():
    from via_ai.orchestration import fit_context

    c = context()
    assert fit_context(ScriptedProvider([]), c, lambda c: 10**9) is c


def test_the_response_schema_is_counted_in_the_prompt_budget():
    """Groq counts the schema sent with the prompt; a request that only just fits without it must not be sent."""
    big = context().model_copy(update={"net_names": [f"NET{i}" for i in range(600)]})
    provider = ScriptedProvider([])
    provider.input_token_budget = 3500
    sizes = []
    original = provider.generate_structured

    def spy(request, schema):
        text = (request.system or "") + "".join(m.content for m in request.messages)
        sizes.append(len(text) + len(__import__("json").dumps(schema.model_json_schema())))
        return original(request, schema)

    provider.generate_structured = spy
    with contextlib.suppress(Exception):  # the scripted provider has nothing queued; only the size matters
        explain(provider, big, "Why?")
    assert sizes and sizes[0] // 3 <= 3500


def test_design_rules_in_the_context_can_be_cited_but_invented_ones_cannot():
    from via_ai.schemas import Reference
    from via_ai.verification import verify

    ctx = context(design_rules={"rules_source": "board_file", "min_via_diameter": 0.4, "min_via_drill": 0.3})
    ok = GOOD.model_copy(update={"references": [Reference(kind="design_rule", id="min_via_drill")], "numbers_used": []})
    assert verify(ok, ctx).ok
    bad = GOOD.model_copy(
        update={"references": [Reference(kind="design_rule", id="min_hole_to_hole")], "numbers_used": []}
    )
    report = verify(bad, ctx)
    assert not report.ok and report.unknown_references == ["design_rule:min_hole_to_hole"]
    assert not verify(ok, context()).ok  # no rules in the context: nothing to cite
    assert not verify(ok.model_copy(update={"references": [Reference(kind="design_rule", id="rules_source")]}), ctx).ok


def _entry(i: int, text: str = "Join the outline into one closed loop."):
    from via_ai import ContextKnowledge

    return ContextKnowledge(id=f"k-{i}", version=1, category="manufacturing_constraint", title=f"Note {i}", text=text,
                            verification="unverified", source="own bench", score=0.4)  # fmt: skip


def test_only_retrieved_knowledge_can_be_cited_and_citations_are_reported():
    from via_ai.schemas import Reference
    from via_ai.verification import cited_knowledge, verify

    ctx = context(knowledge=[_entry(1), _entry(2)])
    cited = GOOD.model_copy(update={"references": [Reference(kind="knowledge", id="k-2")], "numbers_used": []})
    assert verify(cited, ctx).ok and cited_knowledge(cited) == {"k-2"}
    invented = GOOD.model_copy(update={"references": [Reference(kind="knowledge", id="k-9")], "numbers_used": []})
    report = verify(invented, ctx)
    assert not report.ok and report.unknown_references == ["knowledge:k-9"]
    assert not verify(cited, context()).ok  # nothing retrieved, nothing citable


def test_trimming_drops_board_lists_first_then_knowledge_then_findings():
    from via_ai.orchestration import fit_context
    from via_ai.prompts import review_messages

    big = context(knowledge=[_entry(i, "Detail. " * 80) for i in range(3)]).model_copy(
        update={"net_names": [f"NET{i}" for i in range(400)]}
    )
    provider = ScriptedProvider([])
    size = lambda c: sum(map(len, review_messages(c)))  # noqa: E731

    provider.input_token_budget = (size(big) - 2000) // 3  # trimming some of the nets is enough
    fitted = fit_context(provider, big, size)
    assert len(fitted.knowledge) == 3 and len(fitted.net_names) < 400 and fitted.findings == big.findings

    lean = big.model_copy(update={"net_names": [], "components": [], "knowledge": []})
    provider.input_token_budget = (
        size(lean) // 3 + 60
    )  # room for the findings and the trim note, but not for any knowledge
    fitted = fit_context(provider, big, size)
    assert fitted.net_names == [] and fitted.components == [] and fitted.knowledge == [] and len(fitted.findings) == 1
    assert fitted.truncated["knowledge"] == 3
