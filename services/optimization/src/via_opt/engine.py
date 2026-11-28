# ruff: noqa: E501
"""VIA Optimize: generate candidates for the requested objectives, validate and compare them.

Nothing here changes the original design. Each candidate is an explicit change set, measured with
the same metrics as the baseline, validated by re-running VIA's checks on the modified design, and
compared on a Pareto front over the requested objectives.
"""

from __future__ import annotations

import hashlib
import json
import time
from collections.abc import Callable, Mapping
from typing import Any

from pydantic import BaseModel, ConfigDict, Field

from via_opt import analysis
from via_opt.algorithms import copper, outline, placement
from via_opt.candidates import Candidate, CandidateStatus, Validation, ValidationStatus
from via_opt.changes import Change, ChangeKind, Target, apply
from via_opt.comparison import pareto_front
from via_opt.constraints import Constraints
from via_opt.modules import spec_for
from via_opt.objectives import METRIC_FOR, Objective, metrics
from via_opt.ranking import rank
from via_opt.validation import validate
from via_pcb.analysis import default_engine
from via_pcb.analysis.context import AnalysisContext
from via_pcb.models import PCBDesign

OPTIMIZER_VERSION = "1.1.0"

#: Human-readable metric names and units, for benefits/trade-offs text.
LABELS = {
    "board_area_mm2": ("board area", "mm²"),
    "ratsnest_mm": ("unrouted connection length (ratsnest)", "mm"),
    "routed_length_mm": ("routed track length", "mm"),
    "via_count": ("via count", ""),
    "copper_layers_used": ("copper layers used", ""),
    "manufacturing_issues": ("manufacturing issues", ""),
    "current_capacity_issues": ("current-capacity issues", ""),
    "cost_index": ("relative cost index", ""),
}


class OptimizationResult(BaseModel):
    model_config = ConfigDict(extra="forbid")

    optimizer_version: str = OPTIMIZER_VERSION
    objectives: list[Objective]
    baseline: dict[str, float | None]
    candidates: list[Candidate]
    pareto: list[str] = Field(description="Candidate keys no other candidate beats on every requested objective")
    notes: list[str] = Field(default_factory=list)
    analysis: dict[str, Any] = Field(default_factory=dict, description="Area and manufacturing-margin measurements")


def _deltas(before: dict[str, float | None], after: dict[str, float | None]) -> tuple[list[str], list[str]]:
    better: list[str] = []
    worse: list[str] = []
    for k, (label, unit) in LABELS.items():
        b, a = before.get(k), after.get(k)
        if b is None or a is None or abs(a - b) < 1e-6:
            continue
        pct = f" ({(a - b) / b * 100:+.1f}%)" if b else ""
        text = f"{label}: {b:g} -> {a:g}{(' ' + unit) if unit else ''}{pct}"
        (better if a < b else worse).append(text)
    return better, worse


def _candidate(
    design: PCBDesign,
    key: str,
    algorithm: str,
    version: str,
    objectives: list[Objective],
    title: str,
    summary: str,
    changes: list[Change],
    cons: Constraints,
    options: dict[str, Any],
    baseline: dict[str, float | None],
    extra_trade_offs: list[str] | None = None,
    details: dict[str, Any] | None = None,
    execution: dict[str, Any] | None = None,
) -> Candidate:
    started = time.perf_counter()
    validation, after = validate(design, changes, cons, options)
    after_metrics = metrics(after, options) if after is not None else {}
    benefits, worse = _deltas(baseline, after_metrics)
    trade_offs = worse + (extra_trade_offs or []) + validation.notes
    status = {
        ValidationStatus.PASSED: CandidateStatus.VALIDATED,
        ValidationStatus.FAILED: CandidateStatus.REJECTED,
        ValidationStatus.REQUIRES_REROUTING: CandidateStatus.AWAITING_VALIDATION,
        ValidationStatus.MANUAL: CandidateStatus.PROPOSED,
        ValidationStatus.UNVERIFIED: CandidateStatus.AWAITING_VALIDATION,
    }[validation.status]
    return finish(
        Candidate(
            key=key,
            algorithm=algorithm,
            algorithm_version=version,
            objectives=[o.value for o in objectives],
            title=title,
            summary=summary,
            changes=changes,
            metrics_before=baseline,
            metrics_after=after_metrics,
            expected_benefits=benefits,
            trade_offs=trade_offs,
            validation=validation,
            status=status,
            details=details or {},
        ),
        started,
        execution,
    )


def _rect_area(after: dict[str, Any]) -> float:
    return float((after["max_x"] - after["min_x"]) * (after["max_y"] - after["min_y"]))


def _hash(c: Candidate) -> str:
    canonical = {
        "algorithm": c.algorithm,
        "version": c.algorithm_version,
        "changes": [ch.model_dump(mode="json") for ch in c.changes],
    }
    return hashlib.sha256(json.dumps(canonical, sort_keys=True, separators=(",", ":")).encode()).hexdigest()


def finish(c: Candidate, started: float, execution: dict[str, Any] | None = None) -> Candidate:
    """Adds what every candidate carries: hash, warnings, limitations and execution metadata."""
    spec = spec_for(c.key)
    c.candidate_hash = _hash(c)
    c.limitations = [
        *(spec.limitations if spec else []),
        "'Validated' means VIA's own checks found no new problem; KiCad DRC runs only after a change set is applied.",
    ]
    c.warnings = [
        *c.validation.notes,
        *(
            f"{len(c.validation.new_problems)} new problem(s) seen on the modified design."
            for _ in [0]
            if c.validation.new_problems
        ),
    ]
    c.execution = {
        "deterministic": True,
        "seed": None,
        **(execution or {}),
        "evaluation_seconds": round(time.perf_counter() - started, 3),
    }
    return c


def optimize(
    design: PCBDesign,
    objectives: list[Objective],
    cons: Constraints | None = None,
    options: dict[str, Any] | None = None,
    weights: Mapping[Objective, float] | None = None,
    progress: Callable[[str], None] | None = None,
) -> OptimizationResult:
    """``progress`` is told the phase being worked on (never a percentage: the work isn't measurable ahead of time)."""
    say = progress or (lambda _: None)
    cons = cons or Constraints()
    options = dict(options or {})
    ctx = AnalysisContext(design=design, options=options)
    profile = ctx.profile
    say("Measuring the original design")
    baseline = metrics(design, options)
    wanted = set(objectives)
    cands: list[Candidate] = []
    notes: list[str] = []
    measured: dict[str, Any] = {}
    if wanted & {Objective.AREA, Objective.PLACEMENT, Objective.COST}:
        say("Analysing board area")
        measured["area"] = analysis.area_analysis(design)
    if wanted & {Objective.MANUFACTURABILITY, Objective.COST}:
        say("Measuring manufacturing margins")
        measured["margins"] = analysis.margin_analysis(design, options, profile)

    if wanted & {Objective.AREA, Objective.COST}:
        say("Board area")
        changes, why = outline.outline_fit(design, cons, profile)
        if changes:
            cands.append(
                _candidate(
                    design,
                    "outline_fit",
                    "outline_fit",
                    outline.VERSION,
                    [Objective.AREA, Objective.COST],
                    "Fit the board outline to its content",
                    changes[0].reason,
                    changes,
                    cons,
                    options,
                    baseline,
                    ["Less margin around the parts: check enclosure fit and mounting."],
                )
            )
        else:
            notes.append(f"Area: {why}")

    if wanted & {Objective.MANUFACTURABILITY, Objective.COST}:
        say("Manufacturability")
        vias, blocked = copper.standardize_vias(ctx, profile)
        if vias:
            cands.append(
                _candidate(
                    design,
                    "via_standardization",
                    "standardize_vias",
                    copper.VERSION,
                    [Objective.MANUFACTURABILITY, Objective.COST],
                    f"Bring vias up to {profile.name}",
                    f"{len(vias)} via(s) resized to meet the profile where clearance allows.",
                    vias,
                    cons,
                    options,
                    baseline,
                    ["Larger vias take more routing space."],
                    {"blocked_vias": blocked},
                )
            )
        if blocked:
            notes.append(
                f"Manufacturability: {len(blocked)} via(s) can't grow without breaking {profile.min_clearance:g} mm clearance."
            )
        narrow = copper.widen_tracks(ctx, {}, profile, "Widen to the profile minimum ({target:g} mm); reached {achieved:g} mm.",
                                     min_targets=profile.min_track_width)  # fmt: skip
        if narrow:
            cands.append(
                _candidate(
                    design,
                    "track_min_width",
                    "widen_tracks",
                    copper.VERSION,
                    [Objective.MANUFACTURABILITY, Objective.COST],
                    f"Widen tracks below {profile.min_track_width:g} mm",
                    f"{len(narrow)} track segment(s) widened towards the profile minimum where clearance allows.",
                    narrow,
                    cons,
                    options,
                    baseline,
                )
            )
        if not vias and not narrow:
            notes.append(f"Manufacturability: tracks and vias already meet {profile.name} (or can't grow).")

    if Objective.THERMAL in wanted:
        say("Current capacity")
        power = options.get("power")
        targets = copper.power_targets(ctx, power) if isinstance(power, dict) else {}
        if not targets:
            notes.append("Thermal: needs current requirements per net (options.power) and a copper thickness.")
        else:
            wide = copper.widen_tracks(
                ctx, targets, profile, "IPC-2221 width for {net}: {target:.3f} mm; reached {achieved:g} mm."
            )
            if wide:
                cands.append(
                    _candidate(
                        design,
                        "power_track_widening",
                        "widen_tracks",
                        copper.VERSION,
                        [Objective.THERMAL],
                        "Widen power tracks for their current",
                        f"{len(wide)} segment(s) widened towards IPC-2221 widths.",
                        wide,
                        cons,
                        options,
                        baseline,
                        ["Wider tracks take more routing space."],
                        {"targets_mm": {k: round(v, 3) for k, v in targets.items()}},
                    )
                )
            else:
                notes.append("Thermal: power tracks already meet their targets, or can't grow within clearance.")

    if wanted & {Objective.PLACEMENT, Objective.ROUTING}:
        say("Placement")
        placed = placement.improve_placement(design, cons)
        moves = placed.changes
        n_rot = sum(1 for ch in moves if ch.kind == ChangeKind.ROTATE_COMPONENT)
        if moves:
            cands.append(
                _candidate(
                    design,
                    "placement_ratsnest",
                    "annealing_ratsnest",
                    placement.VERSION,
                    [Objective.PLACEMENT, Objective.ROUTING],
                    "Move parts closer to what they connect to",
                    f"{len(moves) - n_rot} component(s) moved and {n_rot} rotated; "
                    f"ratsnest {placed.before:.1f} -> {placed.after:.1f} mm.",
                    moves,
                    cons,
                    options,
                    baseline,
                    ["Changes the layout: affected parts must be re-routed."],
                    {"search": placed.execution},
                    execution={**placed.execution, "deterministic": not placed.execution.get("budget_exhausted")},
                )
            )
            if Objective.AREA in wanted and not cons.outline_fixed:
                packed = apply(design, moves)
                fit, _ = outline.outline_fit(packed, cons, profile)
                plain = next((c for c in cands if c.key == "outline_fit"), None)
                new_area = _rect_area(fit[0].after) if fit else None
                if new_area is not None and (plain is None or new_area < _rect_area(plain.changes[0].after) * 0.99):
                    cands.append(
                        _candidate(
                            design,
                            "placement_compaction",
                            "annealing_ratsnest+outline_fit",
                            placement.VERSION,
                            [Objective.AREA, Objective.PLACEMENT, Objective.COST],
                            "Re-place parts, then fit the outline",
                            f"{fit[0].reason} after the placement changes.",
                            [*moves, *fit],
                            cons,
                            options,
                            baseline,
                            [
                                "Changes the layout: affected parts must be re-routed.",
                                "Less margin around the parts: check enclosure fit and mounting.",
                            ],
                            execution={
                                **placed.execution,
                                "deterministic": not placed.execution.get("budget_exhausted"),
                            },
                        )
                    )
        else:
            notes.append("Placement: no move that shortens connections fits within the constraints.")

    if Objective.LAYERS in wanted:
        say("Layer usage")
        usage = default_engine().run(design, options=options, only={"copper_layer_usage"})
        unused = [f.objects[0].id for f in usage.findings]
        count = design.stats.copper_layer_count
        if unused and count > 2:
            target = max(2, count - len(unused))
            target += target % 2
            if target < count:
                change = Change(kind=ChangeKind.SET_COPPER_LAYER_COUNT, target=Target(kind="stackup", id="stackup", label="Copper layers"),
                                before={"count": count, "unused": unused}, after={"count": target},
                                reason=f"{', '.join(unused)} carry no routing; a {target}-layer stackup may suffice.")  # fmt: skip
                cands.append(finish(Candidate(
                    key="layer_reduction", algorithm="layer_usage", algorithm_version="1.0.0", objectives=[Objective.LAYERS.value, Objective.COST.value],
                    title=f"Consider a {target}-layer board", summary=change.reason, changes=[change], metrics_before=baseline, metrics_after={},
                    expected_benefits=[f"copper layers: {count} -> {target}"],
                    trade_offs=["Needs a new stackup and re-check of impedance and plane strategy in KiCad.", "Unused layers may be planned for shielding or symmetry."],
                    validation=Validation(status=ValidationStatus.MANUAL, notes=["Layer count changes are made in KiCad, not exported by VIA."]),
                    status=CandidateStatus.PROPOSED,
                ), time.perf_counter()))  # fmt: skip
        else:
            notes.append("Layers: every copper layer carries routing.")

    say("Comparing candidates")
    keys = [METRIC_FOR[o] for o in objectives]
    rank(cands, baseline, weights or {})
    points = {c.key: c.metrics_after for c in cands if c.metrics_after and c.status != CandidateStatus.REJECTED}
    return OptimizationResult(
        objectives=list(objectives),
        baseline=baseline,
        candidates=cands,
        pareto=pareto_front(points, keys) if points else [],
        notes=notes,
        analysis=measured,
    )
