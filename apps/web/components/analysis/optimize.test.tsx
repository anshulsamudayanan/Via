import type { CandidateDetail, OptimizationComparison, OptimizationRun } from "@via/types";
import { screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it, vi } from "vitest";

import { mockClient, renderWith } from "@/test/helpers";

import { buildQuantityBody, constraintsBody, DEFAULT_CONSTRAINTS, weightsBody } from "./optimize-options";
import { OptimizePanel } from "./optimize-panel";

const baseline = { board_area_mm2: 1200, ratsnest_mm: null, via_count: 0 };

function run(overrides: Partial<OptimizationRun> = {}): OptimizationRun {
  return {
    id: "run1", design_id: "d1", revision_id: "r1", revision_number: 1, status: "succeeded", attempt: 1,
    config: { objectives: ["area", "cost"] }, optimizer_version: "1.1.0", error_code: null, error_message: null,
    created_at: "2026-11-28T10:00:00Z", finished_at: "2026-11-28T10:00:05Z",
    summary: { baseline, notes: [], pareto: ["outline_fit"], candidate_count: 1 },
    ...overrides,
  };
}

function candidate(overrides: Partial<CandidateDetail> = {}): CandidateDetail {
  return {
    id: "c1", run_id: "run1", key: "outline_fit", algorithm: "outline_fit", algorithm_version: "1.0.0", objectives: ["area"],
    title: "Fit the board outline to its content", summary: "Shrinks the outline.", metrics_before: { board_area_mm2: 1200 },
    metrics_after: { board_area_mm2: 39 }, expected_benefits: ["board area: 1200 -> 39 mm²"], trade_offs: ["Less margin"],
    validation: { status: "passed", checks_run: [], new_problems: [], resolved_problems: 0, constraint_violations: [], notes: [] },
    pareto: true, status: "validated", status_reason: null, change_count: 1, exportable_changes: 1, lifecycle: "validated",
    constraints_evaluated: [
      { id: "component_identity", kind: "hard", status: "satisfied", detail: "", violations: [] },
      { id: "requirement:emc", kind: "hard", status: "unverified", detail: "VIA has no evaluator for this requirement", violations: [] },
      { id: "outline_fixed", kind: "hard", status: "not_applicable", detail: "", violations: [] },
    ],
    warnings: [], limitations: ["Only rectangular outlines are resized."], execution: { seed: null, deterministic: true },
    score: null, candidate_hash: "ab".repeat(32), applied_revision: null, changes: [], details: {},
    ...overrides,
  };
}

const comparison: OptimizationComparison = {
  objectives: ["area"], metrics: ["board_area_mm2", "ratsnest_mm"], baseline,
  rows: [{ id: "c1", key: "outline_fit", title: "Fit the board outline", status: "validated", metrics: { board_area_mm2: 39, ratsnest_mm: null }, deltas: { board_area_mm2: -1161, ratsnest_mm: null } }],
  pareto: ["c1"], dominance: {},
};

function render(client: ReturnType<typeof mockClient>, canEdit = true) {
  return renderWith(<OptimizePanel projectId="p1" isOwner designId="d1" revisionId="r1" canEdit={canEdit} onHighlight={vi.fn()} onChangeSetCreated={vi.fn()} />, client);
}

describe("option parsing", () => {
  it("builds the constraints body from the form and rejects out-of-range numbers", () => {
    const ok = constraintsBody({ ...DEFAULT_CONSTRAINTS, fixed_components: "J1, U3  R9", max_board_width_mm: "80", requirements: [{ kind: " emc ", description: "x", hard: false }, { kind: " ", description: "", hard: true }] });
    expect(ok).toEqual({ ok: true, value: expect.objectContaining({ edge_margin_mm: 1, component_gap_mm: 0.25, fixed_components: ["J1", "U3", "R9"], max_board_width_mm: 80, requirements: [{ kind: "emc", description: "x", hard: false }] }) });
    expect(constraintsBody({ ...DEFAULT_CONSTRAINTS, edge_margin_mm: "99" })).toEqual({ ok: false, error: "Edge margin must be between 0 and 50." });
    expect(constraintsBody({ ...DEFAULT_CONSTRAINTS, component_gap_mm: "" })).toEqual({ ok: false, error: "Component gap is required." });
  });

  it("sends weights only for chosen objectives and a build quantity only when valid", () => {
    expect(weightsBody({ area: "3", cost: "" }, new Set(["area", "cost"]))).toEqual({ ok: true, value: { area: 3 } });
    expect(weightsBody({}, new Set(["area"]))).toEqual({ ok: true, value: undefined });
    expect(weightsBody({ area: "-1" }, new Set(["area"]))).toEqual({ ok: false, error: "Weights must be between 0 and 1000." });
    expect(buildQuantityBody("")).toEqual({ ok: true, value: undefined });
    expect(buildQuantityBody("25")).toEqual({ ok: true, value: 25 });
    expect(buildQuantityBody("0").ok).toBe(false);
  });
});

describe("OptimizePanel", () => {
  it("starts a run with the constraints and weights the engineer entered", async () => {
    const start = vi.fn().mockResolvedValue(run({ status: "queued" }));
    const client = mockClient({ optimization: { start } });
    render(client);
    await userEvent.click(await screen.findByText("Constraints"));
    await userEvent.clear(screen.getByLabelText("Edge margin (mm)"));
    await userEvent.type(screen.getByLabelText("Edge margin (mm)"), "2");
    await userEvent.click(screen.getByRole("button", { name: "Add requirement" }));
    await userEvent.type(screen.getByLabelText("Requirement kind"), "enclosure_fit");
    await userEvent.click(screen.getByText("Preference weights"));
    await userEvent.type(screen.getByRole("textbox", { name: "Board area" }), "3");
    await userEvent.click(screen.getByRole("button", { name: "Generate candidates" }));
    await waitFor(() => expect(start).toHaveBeenCalled());
    const body = start.mock.calls[0]![1];
    expect(body.objectives).toEqual(["area", "manufacturability"]);
    expect(body.constraints).toEqual(expect.objectContaining({ edge_margin_mm: 2, requirements: [{ kind: "enclosure_fit", description: "", hard: true }] }));
    expect(body.weights).toEqual({ area: 3 });
    expect(body.build_quantity).toBeUndefined();
  });

  it("shows an invalid number instead of calling the API", async () => {
    const start = vi.fn();
    render(mockClient({ optimization: { start } }));
    await userEvent.click(await screen.findByText("Constraints"));
    await userEvent.clear(screen.getByLabelText("Edge margin (mm)"));
    await userEvent.type(screen.getByLabelText("Edge margin (mm)"), "500");
    await userEvent.click(screen.getByRole("button", { name: "Generate candidates" }));
    expect(await screen.findByText("Edge margin must be between 0 and 50.")).toBeTruthy();
    expect(start).not.toHaveBeenCalled();
  });

  it("asks the owner for consent before pricing and never offers a quantity without it", async () => {
    const grant = vi.fn().mockResolvedValue({ granted: true, granted_at: "t", policy_version: "v" });
    const client = mockClient({ optimization: { supplierStatus: vi.fn().mockResolvedValue({ provider: "mouser", configured: true }), supplierConsent: vi.fn().mockResolvedValue({ granted: false, granted_at: null, policy_version: "v" }), grantSupplierConsent: grant } });
    render(client);
    await userEvent.click(await screen.findByLabelText("Relative cost"));
    await userEvent.click(await screen.findByText("Supplier pricing (Mouser)"));
    expect(screen.queryByLabelText("Boards to build")).toBeNull();
    await userEvent.click(await screen.findByRole("button", { name: "Allow Mouser lookups for this project" }));
    expect(grant).toHaveBeenCalledWith("p1");
    expect(await screen.findByLabelText("Boards to build")).toBeTruthy();
  });

  it("says pricing isn't set up when the server has no key", async () => {
    render(mockClient());
    await userEvent.click(await screen.findByLabelText("Relative cost"));
    await userEvent.click(await screen.findByText("Supplier pricing (Mouser)"));
    expect(await screen.findByText(/MOUSER_API_KEY/)).toBeTruthy();
  });

  it("shows what a running optimization is doing without a percentage", async () => {
    const client = mockClient({ optimization: { runs: vi.fn().mockResolvedValue([run({ status: "running", summary: { phase: "Placement" } })]) } });
    render(client);
    const phase = await screen.findByText(/Placement…/);
    expect(phase.textContent).not.toContain("%");
    expect(screen.getByText(/no percentage/)).toBeTruthy();
  });

  it("lists candidates with their lifecycle, the comparison with the original, and a report link", async () => {
    const c = candidate();
    const client = mockClient({ optimization: { runs: vi.fn().mockResolvedValue([run()]), candidates: vi.fn().mockResolvedValue([c]), compare: vi.fn().mockResolvedValue(comparison), candidate: vi.fn().mockResolvedValue(c) } });
    render(client);
    expect(await screen.findByText("Passed VIA checks")).toBeTruthy();
    const table = (await screen.findByText("Metric (lower is better)")).closest("table")!;
    expect(within(table).getByText("Original")).toBeTruthy();
    expect(within(table).queryByText(/ratsnest/i)).toBeNull(); // never calculated on the original, so not shown
    expect(within(table).getByText("Board area")).toBeTruthy();
    expect(screen.getByRole("link", { name: /Report/ }).getAttribute("href")).toBe("/report.md");
    await userEvent.click(screen.getByRole("button", { name: /Fit the board outline to its content/ }));
    expect(await screen.findByText("Constraints checked")).toBeTruthy();
    expect(screen.getByText("Not verified (1)")).toBeTruthy();
    expect(screen.getByText(/requirement:emc: VIA has no evaluator/)).toBeTruthy();
    expect(screen.getByText("Only rectangular outlines are resized.")).toBeTruthy();
  });

  it("only offers Accept for candidates that passed, and labels the others honestly", async () => {
    const needs = candidate({ id: "c2", status: "awaiting_validation", lifecycle: "needs_review", validation: { ...candidate().validation, status: "requires_rerouting" } });
    const client = mockClient({ optimization: { runs: vi.fn().mockResolvedValue([run()]), candidates: vi.fn().mockResolvedValue([needs]), compare: vi.fn().mockResolvedValue({ ...comparison, rows: [] }), candidate: vi.fn().mockResolvedValue(needs) } });
    render(client);
    expect(await screen.findByText("Needs review")).toBeTruthy();
    expect(screen.getByText("Needs re-routing")).toBeTruthy();
    await userEvent.click(screen.getByRole("button", { name: /Fit the board outline to its content/ }));
    expect((await screen.findByRole("button", { name: "Accept" })).hasAttribute("disabled")).toBe(true);
  });

  it("shows the analysis: area, margins and a partial price list that says what it covers", async () => {
    const analysis = {
      area: { available: true, observations: ["24.5 mm of the right side of the outline holds no parts, tracks, vias or zones."], board_width_mm: 40, board_height_mm: 30, outline_area_mm2: 1200, rectangular: true, occupied_area_mm2: 2, utilisation: 0.0017, resolution_mm: 0.17, unused_margin_mm: { left: 4.5, top: 4.5, right: 24.5, bottom: 24.5 }, largest_empty_rectangle: { area_mm2: 980, width_mm: 40, height_mm: 24.5, x_mm: 0, y_mm: 5.5 }, density_grid: [[0, 0], [0, 0]] },
      margins: { profile: { key: "via-conservative", name: "VIA conservative", source: "" }, risk_fraction: 0.25, violating_features: 1, potential_risk_features: 2, notes: ["VIA can't state that a design is manufacturable"], rules: [{ check: "mfg_track_width", title: "Track width", ran: true, limits: { min_track_width: 0.15 }, violating_features: 1, potential_risk_features: 2 }] },
      bom: { status: "partial" as const, supplier: "mouser", currency: "USD", build_quantity: 10, lines: 3, lines_priced: 1, notes: ["Prices are the supplier's own listing"], unpriced: [{ key: "k", references: ["U1"], reason: "No manufacturer part number in the design" }],
        strategies: { cheapest: { total: 2, lines: [{ key: "a", references: ["R1", "R2"], mpn: "RC-10K", needed: 20, order_qty: 100, overbuy: 80, unit_price: 0.05, total: 5, in_stock: false, lead_time_days: 14, supplier_part_number: "S1", url: null }] }, fastest: { total: 3, lines: [] } } },
    };
    const client = mockClient({ optimization: { runs: vi.fn().mockResolvedValue([run({ summary: { baseline, analysis } })]), candidates: vi.fn().mockResolvedValue([]), compare: vi.fn() } });
    render(client);
    expect(await screen.findByText(/Covered by parts/)).toBeTruthy();
    expect(screen.getByText(/1 feature break it; 2 more are within 25% above a limit/)).toBeTruthy();
    expect(screen.getByText(/1 of 3 BOM lines priced/)).toBeTruthy();
    expect(screen.getByText(/The totals cover only the priced lines/)).toBeTruthy();
    expect(screen.getByText("RC-10K")).toBeTruthy();
    expect(screen.getByText(/not in stock · 14 days/)).toBeTruthy();
    await userEvent.click(screen.getByText(/Not priced \(1\)/));
    expect(screen.getByText(/No manufacturer part number in the design/)).toBeTruthy();
    expect(screen.getByRole("button", { name: /Fastest/ })).toBeTruthy();
  });
});
