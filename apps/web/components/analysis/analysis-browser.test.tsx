import type { FindingListItem, FindingListPage, RunListItem } from "@via/types";
import { screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, describe, expect, it, vi } from "vitest";

import { mockClient, navigation, page, renderWith, router } from "@/test/helpers";

import { AnalysisBrowser } from "./analysis-browser";

const finding = (o: Partial<FindingListItem> = {}): FindingListItem => ({
  id: "f1", run_id: "run1", design: { id: "d1", name: "Motor board" }, project: { id: "p1", name: "Motor Controller" },
  revision_id: "r2", revision_number: 2, check_id: "board_outline", rule: "outline_open", category: "manufacturing",
  severity: "high", source: "via_deterministic", verification: "verified", title: "Board outline is open", status: "open",
  components: [], nets: [], created_at: "2026-11-25T10:00:00Z", ...o,
});
const findingsPage = (items: FindingListItem[], o: Partial<FindingListPage> = {}): FindingListPage => ({
  ...page(items), by_severity: { high: 1, low: 4 }, designs_analysed: 3, ...o,
});

beforeEach(() => {
  navigation.pathname = "/analysis";
  navigation.search = new URLSearchParams();
  router.replace.mockReset();
});

describe("AnalysisBrowser", () => {
  it("shows open findings across designs with severity totals, linking to the finding in its design", async () => {
    const browseFindings = vi.fn().mockResolvedValue(findingsPage([finding(), finding({ id: "f2", severity: "low", rule: "copper_pad_no_net", title: "Pad without net", components: ["R1"] })]));
    renderWith(<AnalysisBrowser />, mockClient({ analysis: { browseFindings }, projects: { list: vi.fn().mockResolvedValue(page([])) } }));

    const list = await screen.findByRole("list", { name: "Findings" });
    const link = within(list).getByRole("link", { name: /Board outline is open/ });
    expect(link.getAttribute("href")).toBe("/projects/p1/designs/d1?tab=analysis&revision=r2&finding=f1");
    expect(within(list).getByText("R1")).toBeTruthy();
    expect(screen.getByText("latest analysis of 3 designs")).toBeTruthy();
    const high = screen.getByRole("button", { name: /high/i });
    expect(high.textContent).toContain("1");
    expect(browseFindings).toHaveBeenCalledWith(expect.objectContaining({ status: "open", offset: 0 }), expect.anything());

    await userEvent.click(high);
    expect(router.replace).toHaveBeenLastCalledWith("/analysis?severity=high", { scroll: false });
  });

  it("says so when nothing has been analysed yet", async () => {
    const browseFindings = vi.fn().mockResolvedValue(findingsPage([], { by_severity: {}, designs_analysed: 0 }));
    renderWith(<AnalysisBrowser />, mockClient({ analysis: { browseFindings }, projects: { list: vi.fn().mockResolvedValue(page([])) } }));
    expect(await screen.findByText("No analyses yet")).toBeTruthy();
  });

  it("lists runs with status, severities and failures", async () => {
    navigation.search = new URLSearchParams("view=runs&status=failed");
    const run = (o: Partial<RunListItem>): RunListItem => ({
      id: "run1", status: "succeeded", design: { id: "d1", name: "Motor board" }, project: { id: "p1", name: "Motor Controller" },
      project_archived: false, revision_id: "r2", revision_number: 2, finding_count: 5, by_severity: { high: 1, low: 4 }, error_code: null,
      triggered_by: { id: "u1", display_name: "Ada Lovelace" }, created_at: "2026-11-25T10:00:00Z", finished_at: "2026-11-25T10:01:00Z", ...o,
    });
    const browseRuns = vi.fn().mockResolvedValue(page([run({}), run({ id: "run2", status: "failed", finding_count: null, by_severity: {}, error_code: "worker_lost" })]));
    renderWith(<AnalysisBrowser />, mockClient({ analysis: { browseRuns }, projects: { list: vi.fn().mockResolvedValue(page([])) } }));
    const list = await screen.findByRole("list", { name: "Analysis runs" });
    expect(within(list).getByText("1 high")).toBeTruthy();
    expect(within(list).getByText("worker_lost")).toBeTruthy();
    expect(within(list).getAllByRole("link", { name: /Motor board/ })[0]!.getAttribute("href")).toBe("/projects/p1/designs/d1?tab=analysis&revision=r2");
    await waitFor(() => expect(browseRuns).toHaveBeenCalledWith(expect.objectContaining({ status: "failed" }), expect.anything()));
  });
});
