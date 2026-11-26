import type { AnalysisRun, ChangeSet, Finding, FindingDetail, FindingPage } from "@via/types";
import { screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it, vi } from "vitest";

import { mockClient, page, renderWith } from "@/test/helpers";

import { AnalysisPanel } from "./analysis-panel";
import { ChangesPanel } from "./changes-panel";

function run(overrides: Partial<AnalysisRun> = {}): AnalysisRun {
  return {
    id: "run1", design_id: "d1", revision_id: "r1", revision_number: 1, status: "succeeded", attempt: 1, config: {},
    checks: [{ check_id: "kicad_drc", version: "1", status: "ok", finding_count: 1, duration_ms: 10, message: null }],
    summary: { finding_count: 1, by_severity: { critical: 1, high: 0, medium: 0, low: 0, info: 0 }, checks: { ok: 1, skipped: 0, error: 0 } },
    analysis_version: "0.3.0", engine_version: "0.2.0", design_parser_version: "0.2.0", design_schema_version: "1.1.0",
    error_code: null, error_message: null, triggered_by: null, created_at: "2026-11-26T10:00:00Z", started_at: null, finished_at: "2026-11-26T10:00:05Z",
    ...overrides,
  };
}

const finding: Finding = {
  id: "f1", run_id: "run1", project_id: "p1", design_id: "d1", revision_id: "r1", check_id: "kicad_drc", check_version: "1",
  rule: "shorting_items", category: "design_rules", severity: "critical", source: "kicad_drc", verification: "verified", confidence: 1,
  title: "Items short GND and SIG", description: "KiCad reports a short.", explanation: "", suggested_resolution: "Move the track.",
  objects: [], components: ["C1"], nets: ["GND", "SIG"],
  region: { bbox: { min_x: 10, min_y: 10, max_x: 11, max_y: 11 }, points: [], layers: ["F.Cu"] },
  fingerprint: "x", status: "open", status_reason: null, status_changed_at: null, inherited: false, created_at: "2026-11-26T10:00:05Z",
};
const detail: FindingDetail = {
  ...finding,
  evidence: [{ kind: "measurement", label: "Smallest gap", value: "0 mm", numeric_value: 0, unit: "mm", expected: "≥ 0.2 mm" }],
  history: [],
};
const findings: FindingPage = { ...page([finding]), facets: { severity: { critical: 1 }, status: { open: 1 }, category: { design_rules: 1 }, source: { kicad_drc: 1 } } };

describe("AnalysisPanel", () => {
  it("lists findings, shows evidence with its source, and highlights the finding on the board", async () => {
    const client = mockClient({
      analysis: { runs: vi.fn().mockResolvedValue(page([run()])), findings: vi.fn().mockResolvedValue(findings), finding: vi.fn().mockResolvedValue(detail) },
    });
    const onHighlight = vi.fn();
    renderWith(<AnalysisPanel projectId="p1" designId="d1" revisionId="r1" canEdit onHighlight={onHighlight} />, client);
    await userEvent.click(await screen.findByRole("button", { name: /Items short GND and SIG/ }));
    expect(onHighlight).toHaveBeenCalledWith(expect.objectContaining({ references: ["C1"], nets: ["GND", "SIG"], focus: true }));
    const panel = await screen.findByLabelText("Finding details");
    expect(panel.textContent).toContain("KiCad DRC");
    expect(panel.textContent).toContain("Verified");
    expect(panel.textContent).toContain("Smallest gap");
    expect(panel.textContent).toContain("(expected ≥ 0.2 mm)");
    expect(panel.textContent).toContain("AI explanations are off");
    expect(client.analysis.findings).toHaveBeenCalledWith("run1", expect.objectContaining({ status: "open" }), expect.anything());
  });

  it("requires a note to dismiss and sends the review", async () => {
    const review = vi.fn().mockResolvedValue({ ...detail, status: "dismissed" });
    const client = mockClient({
      analysis: { runs: vi.fn().mockResolvedValue(page([run()])), findings: vi.fn().mockResolvedValue(findings), finding: vi.fn().mockResolvedValue(detail), review },
    });
    renderWith(<AnalysisPanel projectId="p1" designId="d1" revisionId="r1" canEdit onHighlight={vi.fn()} />, client);
    await userEvent.click(await screen.findByRole("button", { name: /Items short/ }));
    const dismiss = await screen.findByRole("button", { name: "Dismiss" });
    expect((dismiss as HTMLButtonElement).disabled).toBe(true);
    await userEvent.type(screen.getByLabelText("Review note"), "Intentional net tie");
    await userEvent.click(dismiss);
    await waitFor(() => expect(review).toHaveBeenCalledWith("f1", "dismissed", "Intentional net tie"));
  });

  it("offers to run an analysis when there is none, and viewers can't", async () => {
    const start = vi.fn().mockResolvedValue(run({ status: "queued" }));
    const client = mockClient({ analysis: { runs: vi.fn().mockResolvedValue(page([])), start } });
    const { unmount } = renderWith(<AnalysisPanel projectId="p1" designId="d1" revisionId="r1" canEdit onHighlight={vi.fn()} />, client);
    await userEvent.click(await screen.findByRole("button", { name: /Run analysis/ }));
    expect(start).toHaveBeenCalledWith("d1", { revision_id: "r1" });
    unmount();
    renderWith(<AnalysisPanel projectId="p1" designId="d1" revisionId="r1" canEdit={false} onHighlight={vi.fn()} />, client);
    expect(await screen.findByText(/An editor can run an analysis/)).toBeTruthy();
    expect(screen.queryByRole("button", { name: /Run analysis/ })).toBeNull();
  });

  it("shows a failed run honestly", async () => {
    const client = mockClient({ analysis: { runs: vi.fn().mockResolvedValue(page([run({ status: "failed", error_code: "worker_lost", error_message: "Interrupted." })])) } });
    renderWith(<AnalysisPanel projectId="p1" designId="d1" revisionId="r1" canEdit onHighlight={vi.fn()} />, client);
    expect(await screen.findByText("The analysis failed")).toBeTruthy();
    expect(screen.getByText(/Interrupted\. \(worker_lost\)/)).toBeTruthy();
  });
});

function changeSet(overrides: Partial<ChangeSet> = {}): ChangeSet {
  return {
    id: "cs1", design_id: "d1", base_revision_id: "r1", result_revision_id: null, export_run_id: null, title: "Shrink outline", status: "draft",
    result: {}, error_code: null, error_message: null, created_at: "2026-11-26T10:00:00Z", applied_at: null, rolled_back_at: null,
    changes: [{
      id: "ch1", ordinal: 0, kind: "set_outline_rect", target: { kind: "outline", id: "outline" }, before: { min_x: 0, min_y: 0, max_x: 40, max_y: 30 },
      after: { min_x: 0, min_y: 0, max_x: 20, max_y: 10 }, reason: "fit", source: "via_optimize", origin_candidate_id: "c1", status: "proposed", status_reason: null,
    }],
    ...overrides,
  };
}

describe("ChangesPanel", () => {
  it("applies a draft change set", async () => {
    const apply = vi.fn().mockResolvedValue(changeSet({ status: "applying" }));
    const client = mockClient({ changes: { list: vi.fn().mockResolvedValue([changeSet()]), apply } });
    renderWith(<ChangesPanel designId="d1" currentRevisionId="r1" canEdit onRevisionChanged={vi.fn()} />, client);
    expect(await screen.findByText("20 × 10 mm")).toBeTruthy();
    await userEvent.click(screen.getByRole("button", { name: /Apply/ }));
    expect(apply).toHaveBeenCalledWith("cs1");
  });

  it("offers download, rollback and the before/after comparison for the current applied set", async () => {
    const applied = changeSet({ status: "applied", result_revision_id: "r2", applied_at: "2026-11-26T10:01:00Z", result: { sha256: "b".repeat(64), size_bytes: 2048, verification: "re-parsed" } });
    const rollback = vi.fn().mockResolvedValue({ ...applied, status: "rolled_back" });
    const onRevisionChanged = vi.fn();
    const compare = vi.fn().mockResolvedValue({
      base: { revision_id: "r1", revision_number: 1, analysis_run_id: "a1" }, head: { revision_id: "r2", revision_number: 2, analysis_run_id: "a2" },
      object_counts: {}, findings: { introduced: [], resolved: [{ id: "x", rule: "track_too_narrow", severity: "medium", title: "Narrow track", source: "via_deterministic" }], persisting: 3, base_total: 4, head_total: 3 },
    });
    const client = mockClient({ changes: { list: vi.fn().mockResolvedValue([applied]), rollback, compare } });
    renderWith(<ChangesPanel designId="d1" currentRevisionId="r2" canEdit onRevisionChanged={onRevisionChanged} />, client);
    expect((await screen.findByRole("link", { name: /Download file/ })).getAttribute("href")).toBe("/api/v1/change-sets/cs1/download");
    expect(await screen.findByText(/1 resolved/)).toBeTruthy();
    expect(screen.getByText("Narrow track")).toBeTruthy();
    expect(screen.queryByRole("button", { name: /Apply/ })).toBeNull();
    await userEvent.click(screen.getByRole("button", { name: /Roll back/ }));
    expect(rollback).toHaveBeenCalledWith("cs1");
    await waitFor(() => expect(onRevisionChanged).toHaveBeenCalled());
  });
});
