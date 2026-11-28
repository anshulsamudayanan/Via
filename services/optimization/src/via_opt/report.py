# ruff: noqa: E501
"""Optimization report: a structured, honest summary of one run, built only from what was stored.

Only metrics that were calculated appear; nothing is rounded up into a claim. The report states what 'validated'
means and lists what stayed unverified. ``render_markdown`` turns it into a document an engineer can attach to a
review. Input is plain dicts (the API's stored run and candidates), so the report can be rebuilt from history.
"""

from __future__ import annotations

from collections import Counter
from collections.abc import Mapping, Sequence
from typing import Any

VERIFICATION_STATEMENT = (
    "'Validated' means VIA applied the changes to a copy of the design, re-ran its own checks and the constraints "
    "listed per candidate, and found no new problem. It is not a KiCad DRC result (that runs after a change set is "
    "applied), not an electrical or signal-integrity verification, and not a statement of manufacturability."
)

LABELS = {
    "board_area_mm2": ("Board area", "mm²"),
    "ratsnest_mm": ("Unrouted connection length (ratsnest)", "mm"),
    "routed_length_mm": ("Routed track length", "mm"),
    "via_count": ("Via count", ""),
    "copper_layers_used": ("Copper layers used", ""),
    "manufacturing_issues": ("Manufacturing issues", ""),
    "current_capacity_issues": ("Current-capacity issues", ""),
    "cost_index": ("Relative cost index (illustrative)", ""),
}


def _metrics(before: Mapping[str, Any], after: Mapping[str, Any]) -> list[dict[str, Any]]:
    rows = []
    for key, (label, unit) in LABELS.items():
        b, a = before.get(key), after.get(key)
        if b is None or a is None:
            continue
        delta = round(a - b, 6)
        rows.append(
            {
                "metric": key,
                "label": label,
                "unit": unit,
                "before": b,
                "after": a,
                "delta": delta,
                "percent": round(delta / b * 100, 2) if b else None,
            }
        )
    return rows


def _candidate(c: Mapping[str, Any], baseline: Mapping[str, Any]) -> dict[str, Any]:
    constraints = c.get("constraints_evaluated") or []
    by_status: dict[str, list[str]] = {"satisfied": [], "violated": [], "unverified": [], "not_applicable": []}
    for r in constraints:
        by_status.setdefault(r["status"], []).append(r["id"])
    changes = c.get("changes") or []
    return {
        "key": c["key"],
        "title": c["title"],
        "summary": c.get("summary", ""),
        "algorithm": f"{c['algorithm']} {c['algorithm_version']}",
        "lifecycle": c.get("lifecycle"),
        "status": c["status"],
        "validation_status": (c.get("validation") or {}).get("status"),
        "objectives": c.get("objectives", []),
        "metrics": _metrics(baseline, c.get("metrics_after") or {}),
        "improved": c.get("expected_benefits", []),
        "worse_or_cost": c.get("trade_offs", []),
        "changes": {
            "count": len(changes) or c.get("change_count", 0),
            "by_kind": dict(Counter(ch["kind"] for ch in changes)),
            "exportable": c.get("exportable_changes"),
            "items": [
                f"{ch['kind']} {ch['target'].get('label') or ch['target'].get('id')}: {ch['reason']}"
                for ch in changes[:25]
            ],
        },
        "constraints": by_status,
        "constraint_details": [
            {"id": r["id"], "detail": r.get("detail", "")}
            for r in constraints
            if r["status"] in ("violated", "unverified")
        ],
        "new_problems": (c.get("validation") or {}).get("new_problems", []),
        "warnings": c.get("warnings", []),
        "limitations": c.get("limitations", []),
        "score": c.get("score"),
        "pareto": c.get("pareto", False),
        "candidate_hash": c.get("candidate_hash", ""),
        "execution": c.get("execution", {}),
        "applied_revision": c.get("applied_revision"),
        "status_reason": c.get("status_reason"),
    }


def build_report(run: Mapping[str, Any], candidates: Sequence[Mapping[str, Any]]) -> dict[str, Any]:
    summary = run.get("summary") or {}
    baseline = summary.get("baseline") or {}
    cfg = run.get("config") or {}
    opts = cfg.get("options") or {}
    cands = [_candidate(c, baseline) for c in candidates]
    unverified = sorted({cid for c in cands for cid in c["constraints"].get("unverified", [])})
    return {
        "run": {
            "id": str(run["id"]),
            "design_id": str(run["design_id"]),
            "revision_number": run.get("revision_number"),
            "status": run["status"],
            "optimizer_version": run.get("optimizer_version"),
            "started": run.get("created_at"),
            "finished": run.get("finished_at"),
        },
        "parameters": {
            "objectives": cfg.get("objectives", []),
            "weights": cfg.get("weights"),
            "constraints": cfg.get("constraints", {}),
            "manufacturing_profile": (opts.get("manufacturing_profile") or {}).get("name"),
            "build_quantity": (cfg.get("bom") or {}).get("build_quantity"),
        },
        "baseline": [
            {"metric": k, "label": LABELS[k][0], "unit": LABELS[k][1], "value": baseline[k]}
            for k in LABELS
            if baseline.get(k) is not None
        ],
        "analysis": summary.get("analysis", {}),
        "candidates": cands,
        "pareto": [c["key"] for c in cands if c["pareto"]],
        "notes": summary.get("notes", []),
        "unverified_constraints": unverified,
        "verification_statement": VERIFICATION_STATEMENT,
    }


def _fmt(v: Any, unit: str = "") -> str:
    return f"{v:g}{(' ' + unit) if unit else ''}" if isinstance(v, int | float) else str(v)


def _change(m: Mapping[str, Any]) -> str:
    pct = f" ({m['percent']:+.1f}%)" if m["percent"] is not None else ""
    return f"{m['delta']:+g}{pct}"


def render_markdown(report: Mapping[str, Any]) -> str:
    run, p = report["run"], report["parameters"]
    out = [
        "# VIA Optimize report",
        "",
        f"Design `{run['design_id']}`, revision {run['revision_number']}. Run `{run['id']}` ({run['status']}), optimizer {run['optimizer_version']}.",
        "",
    ]
    out += ["## Parameters", f"- Objectives: {', '.join(p['objectives']) or 'none'}"]
    if p.get("weights"):
        out.append(
            f"- Preference weights: {', '.join(f'{k} {v:g}' for k, v in p['weights'].items())} (display order only)"
        )
    if p.get("manufacturing_profile"):
        out.append(f"- Manufacturing profile: {p['manufacturing_profile']}")
    if p.get("build_quantity"):
        out.append(f"- Build quantity (supplier pricing): {p['build_quantity']}")
    out += ["", "## Original design (calculated metrics)", "", "| Metric | Value |", "|---|---|"]
    out += [f"| {b['label']} | {_fmt(b['value'], b['unit'])} |" for b in report["baseline"]] or [
        "| none calculated | |"
    ]
    area = (report.get("analysis") or {}).get("area") or {}
    if area.get("available"):
        out += [
            "",
            "## Board area",
            f"- {area['board_width_mm']:g} x {area['board_height_mm']:g} mm, {area['outline_area_mm2']:g} mm²; parts occupy about {area['utilisation'] * 100:.1f}% (grid {area['resolution_mm']} mm).",
        ]
        out += [f"- {o}" for o in area.get("observations", [])]
    margins = (report.get("analysis") or {}).get("margins")
    if margins:
        out += [
            "",
            "## Manufacturing margins",
            f"- Profile: {margins['profile']['name']}. {margins['violating_features']} feature(s) break it; {margins['potential_risk_features']} more are within {margins['risk_fraction']:.0%} above a limit (heuristic).",
            f"- {margins['notes'][-1]}",
        ]
    bom = (report.get("analysis") or {}).get("bom")
    if bom:
        out += ["", "## BOM cost (supplier listings)"]
        if bom.get("strategies"):
            out += [
                f"- {bom['supplier']}, {bom['currency']}, build quantity {bom['build_quantity']}; {bom['lines_priced']} of {bom['lines']} lines priced."
            ]
            out += [f"  - {n}: {s['total']:.2f} {bom['currency']}" for n, s in bom["strategies"].items()]
            out += [
                f"- Unpriced: {u['references'][0] if u['references'] else u['key']}: {u['reason']}"
                for u in bom.get("unpriced", [])
            ]
            out += [f"- {n}" for n in bom.get("notes", [])]
        else:
            out += [f"- Not priced: {bom.get('reason') or 'no listing matched'}."]
    out += ["", "## Candidates"]
    if not report["candidates"]:
        out += ["", "No candidate was generated."] + [f"- {n}" for n in report["notes"]]
    for c in report["candidates"]:
        out += [
            "",
            f"### {c['title']} (`{c['key']}`)",
            f"{c['summary']}",
            f"- Lifecycle: **{c['lifecycle']}**; validation: {c['validation_status']}{'; on the Pareto front' if c['pareto'] else ''}.",
            f"- Algorithm {c['algorithm']}; hash `{c['candidate_hash'][:12]}`.",
        ]
        if c["metrics"]:
            out += ["", "| Metric | Before | After | Change |", "|---|---|---|---|"]
            out += [
                f"| {m['label']} | {_fmt(m['before'], m['unit'])} | {_fmt(m['after'], m['unit'])} | {_change(m)} |"
                for m in c["metrics"]
            ]
        else:
            out += ["- No metrics after the change were calculated (a manual change)."]
        out += [
            f"- Changes: {c['changes']['count']} ({', '.join(f'{k} x{v}' for k, v in c['changes']['by_kind'].items())})."
        ]
        if c["worse_or_cost"]:
            out += ["- Got worse or costs something:"] + [f"  - {t}" for t in c["worse_or_cost"]]
        k = c["constraints"]
        out += [
            f"- Constraints: {len(k['satisfied'])} satisfied, {len(k['violated'])} violated, {len(k['unverified'])} unverified, {len(k['not_applicable'])} not applicable."
        ]
        out += [f"  - {d['id']}: {d['detail']}" for d in c["constraint_details"]]
        if c["limitations"]:
            out += ["- Limitations:"] + [f"  - {t}" for t in c["limitations"]]
        if c.get("applied_revision"):
            out += [f"- Applied as revision {c['applied_revision']['revision_number']}."]
    out += ["", "## What this report does not establish", report["verification_statement"]]
    if report["unverified_constraints"]:
        out += [
            "",
            "Constraints declared but not verifiable by VIA: " + ", ".join(report["unverified_constraints"]) + ".",
        ]
    return "\n".join(out) + "\n"
