/** Labels and helpers for findings, optimization metrics and change sets (pure, unit-tested). */

import type { Finding, FindingSource, FindingVerification, Severity } from "@via/types";

import type { Highlight } from "./pcb/overlay";

export const SEVERITIES: Severity[] = ["critical", "high", "medium", "low", "info"];

/** Purple is reserved for interaction, so low and info share the neutral tone (the label tells them apart). */
export function severityTone(s: Severity): "danger" | "warning" | "neutral" {
  if (s === "critical" || s === "high") return "danger";
  if (s === "medium") return "warning";
  return "neutral";
}

/** Where a result came from. Deterministic, KiCad, simulated and AI results are never mixed up. */
export const SOURCE_LABEL: Record<FindingSource, string> = {
  via_deterministic: "VIA check",
  kicad_drc: "KiCad DRC",
  external_simulation: "Simulation",
  ai_suggestion: "AI suggestion",
};

export const VERIFICATION_LABEL: Record<FindingVerification, string> = {
  verified: "Verified",
  heuristic: "Heuristic",
  unverified: "Unverified",
};

/** What to show on the board for a finding: its region, the components and nets it names. */
export function findingHighlight(f: Pick<Finding, "region" | "components" | "nets" | "severity">, focus = true): Highlight {
  return {
    references: f.components,
    nets: f.nets.slice(0, 8),
    regions: f.region ? [{ bbox: f.region.bbox, severity: f.severity, points: f.region.points }] : [],
    focus,
  };
}

export const METRIC_LABEL: Record<string, { label: string; unit: string }> = {
  board_area_mm2: { label: "Board area", unit: "mm²" },
  ratsnest_mm: { label: "Ratsnest length", unit: "mm" },
  routed_length_mm: { label: "Routed length", unit: "mm" },
  cost_index: { label: "Relative cost index", unit: "" },
  copper_layers_used: { label: "Copper layers", unit: "" },
  current_capacity_issues: { label: "Current-capacity issues", unit: "" },
  manufacturing_issues: { label: "Manufacturing issues", unit: "" },
};

export function metricLabel(key: string): string {
  return METRIC_LABEL[key]?.label ?? key.replace(/_/g, " ");
}

function trim(n: number): string {
  return String(Number(n.toFixed(Math.abs(n) >= 100 ? 1 : 3)));
}

/** "−12.5 mm²" / "+3" / "–" (all metrics are minimized, so negative is better). */
export function formatDelta(key: string, delta: number | null | undefined): string {
  if (delta === null || delta === undefined) return "–";
  if (delta === 0) return "0";
  const unit = METRIC_LABEL[key]?.unit;
  return `${delta > 0 ? "+" : "−"}${trim(Math.abs(delta))}${unit ? ` ${unit}` : ""}`;
}

export function formatMetric(key: string, value: number | null | undefined): string {
  if (value === null || value === undefined) return "–";
  const unit = METRIC_LABEL[key]?.unit;
  return `${trim(value)}${unit ? ` ${unit}` : ""}`;
}

export const CHANGE_KIND_LABEL: Record<string, string> = {
  move_component: "Move component",
  rotate_component: "Rotate component",
  set_track_width: "Track width",
  move_via: "Move via",
  set_via_size: "Via size",
  set_outline_rect: "Board outline",
  set_copper_layer_count: "Copper layer count",
};

/** A compact "before → after" for a change, e.g. "0.1 → 0.25 mm" or "(15, 5) → (18, 5)". */
export function describeChange(kind: string, before: Record<string, unknown>, after: Record<string, unknown>): string {
  const n = (v: unknown) => (typeof v === "number" ? trim(v) : "?");
  switch (kind) {
    case "move_component":
    case "move_via":
      return `(${n(before.x)}, ${n(before.y)}) → (${n(after.x)}, ${n(after.y)}) mm`;
    case "rotate_component":
      return `${n(before.rotation)}° → ${n(after.rotation)}°`;
    case "set_track_width":
      return `${n(before.width)} → ${n(after.width)} mm`;
    case "set_via_size":
      return `⌀${n(before.diameter)}/${n(before.drill)} → ⌀${n(after.diameter)}/${n(after.drill)} mm`;
    case "set_outline_rect":
      return `${n(Number(after.max_x) - Number(after.min_x))} × ${n(Number(after.max_y) - Number(after.min_y))} mm`;
    default:
      return JSON.stringify(after);
  }
}
