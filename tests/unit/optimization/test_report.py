# ruff: noqa: E501
"""The report is built from stored data only: no metric appears unless it was calculated."""

from __future__ import annotations

from via_opt.report import build_report, render_markdown

RUN = {
    "id": "r1", "design_id": "d1", "revision_number": 3, "status": "succeeded", "optimizer_version": "1.1.0",
    "created_at": "t0", "finished_at": "t1",
    "config": {"objectives": ["area"], "weights": {"area": 2.0}, "constraints": {}, "options": {"manufacturing_profile": {"name": "VIA conservative"}}, "bom": {"build_quantity": 10}},
    "summary": {"baseline": {"board_area_mm2": 100.0, "ratsnest_mm": None, "via_count": 0, "cost_index": 2.0}, "notes": ["Placement: nothing fits"]},
}  # fmt: skip


def cand(**kw):
    base = {
        "key": "k", "title": "T", "summary": "S", "algorithm": "a", "algorithm_version": "1", "status": "validated", "lifecycle": "validated",
        "objectives": ["area"], "validation": {"status": "passed", "new_problems": []}, "pareto": True, "candidate_hash": "ab" * 32,
        "metrics_after": {"board_area_mm2": 50.0, "ratsnest_mm": 10.0, "via_count": 3, "cost_index": None},
        "expected_benefits": ["board area: 100 -> 50"], "trade_offs": ["Less margin"], "change_count": 1, "exportable_changes": 1,
        "changes": [{"kind": "set_outline_rect", "target": {"id": "Edge.Cuts", "label": "Board outline"}, "reason": "fit"}],
        "constraints_evaluated": [{"id": "component_identity", "status": "satisfied", "detail": ""}, {"id": "requirement:emc", "status": "unverified", "detail": "no evaluator"}, {"id": "outline_fixed", "status": "not_applicable"}],
        "warnings": [], "limitations": ["Only rectangles"], "score": None, "execution": {}, "status_reason": None,
    }  # fmt: skip
    return {**base, **kw}


def test_only_metrics_calculated_before_and_after_appear():
    rep = build_report(RUN, [cand()])
    assert {b["metric"] for b in rep["baseline"]} == {
        "board_area_mm2",
        "via_count",
        "cost_index",
    }  # ratsnest was not calculated
    m = {x["metric"]: x for x in rep["candidates"][0]["metrics"]}
    assert set(m) == {"board_area_mm2", "via_count"}  # ratsnest has no baseline, cost_index has no 'after'
    assert (m["board_area_mm2"]["delta"], m["board_area_mm2"]["percent"]) == (-50.0, -50.0)
    assert m["via_count"]["percent"] is None  # zero baseline: no percentage is invented


def test_unverified_constraints_are_surfaced_and_the_markdown_states_the_limits():
    rep = build_report(RUN, [cand()])
    assert rep["unverified_constraints"] == ["requirement:emc"] and rep["candidates"][0]["constraints"][
        "satisfied"
    ] == ["component_identity"]
    text = render_markdown(rep)
    assert "Build quantity (supplier pricing): 10" in text and "Preference weights: area 2 (display order only)" in text
    assert "1 satisfied, 0 violated, 1 unverified, 1 not applicable" in text and "requirement:emc: no evaluator" in text
    assert "| Board area | 100 mm² | 50 mm² | -50 (-50.0%) |" in text and "ratsnest" not in text.lower().split(
        "candidates"
    )[0].replace("unrouted connection length (ratsnest)", "")
    assert (
        "not a statement of manufacturability" in text
        and "Constraints declared but not verifiable by VIA: requirement:emc" in text
    )


def test_a_run_with_no_candidates_and_a_manual_candidate_render_honestly():
    text = render_markdown(build_report(RUN, []))
    assert "No candidate was generated." in text and "Placement: nothing fits" in text
    manual = cand(metrics_after={}, validation={"status": "manual"}, lifecycle="needs_review", status="proposed")
    assert "No metrics after the change were calculated" in render_markdown(build_report(RUN, [manual]))


def test_bom_section_lists_unpriced_lines_and_never_a_total_without_prices():
    run = {
        **RUN,
        "summary": {
            **RUN["summary"],
            "analysis": {"bom": {"status": "none", "reason": "no listing matched", "strategies": {}}},
        },
    }
    assert "Not priced: no listing matched" in render_markdown(build_report(run, []))
    priced = {"status": "partial", "supplier": "mouser", "currency": "USD", "build_quantity": 10, "lines": 3, "lines_priced": 1,
              "strategies": {"cheapest": {"total": 2.0, "lines": []}}, "unpriced": [{"key": "k", "references": ["U1"], "reason": "No manufacturer part number"}], "notes": ["not a quote"]}  # fmt: skip
    text = render_markdown(build_report({**RUN, "summary": {**RUN["summary"], "analysis": {"bom": priced}}}, []))
    assert (
        "1 of 3 lines priced" in text
        and "cheapest: 2.00 USD" in text
        and "Unpriced: U1: No manufacturer part number" in text
    )


def test_every_documented_module_is_declared_once():
    from via_opt import MODULES

    keys = [m.key for m in MODULES]
    assert len(keys) == len(set(keys))
    expected = {"outline_fit", "via_standardization", "track_min_width", "power_track_widening", "placement_ratsnest", "placement_compaction", "layer_reduction", "area_analysis", "margin_analysis", "bom_cost", "component_alternates", "rerouting", "signal_integrity", "thermal_simulation"}  # fmt: skip
    assert set(keys) == expected
