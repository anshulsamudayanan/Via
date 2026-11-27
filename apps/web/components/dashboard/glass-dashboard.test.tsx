import type { RunListItem } from "@via/types";
import { screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it } from "vitest";

import { bucketRuns, FindingsChart } from "@/components/dashboard/findings-chart";
import { StatCards } from "@/components/dashboard/stat-cards";
import { mockClient, renderWith } from "@/test/helpers";

function run(at: string, by: Record<string, number>, status: RunListItem["status"] = "succeeded"): RunListItem {
  return {
    id: `r-${at}-${status}`, status, design: { id: "d1", name: "Motor board" }, project: { id: "p1", name: "Motor" }, project_archived: false,
    revision_id: "rev1", revision_number: 2, finding_count: Object.values(by).reduce((a, b) => a + b, 0), by_severity: by,
    error_code: null, triggered_by: null, created_at: at, finished_at: at,
  } as RunListItem;
}

describe("findings chart data", () => {
  it("buckets succeeded runs into the last 30 local days, folding low and info together", () => {
    const now = new Date(2026, 10, 27, 15, 0);
    const days = bucketRuns(
      [
        run(new Date(2026, 10, 27, 9).toISOString(), { critical: 1, high: 2, medium: 0, low: 3, info: 1 }),
        run(new Date(2026, 10, 27, 11).toISOString(), { high: 1 }),
        run(new Date(2026, 10, 20, 11).toISOString(), { medium: 5 }),
        run(new Date(2026, 10, 27, 12).toISOString(), { high: 9 }, "failed"), // failed runs report nothing
        run(new Date(2026, 9, 1).toISOString(), { high: 9 }), // older than 30 days
      ],
      now,
    );
    expect(days).toHaveLength(30);
    const today = days[29]!;
    expect(today.values).toEqual([1, 3, 0, 4]); // critical, high, medium, low+info
    expect(today.runs).toBe(2);
    expect(days[22]!.values).toEqual([0, 0, 5, 0]);
    expect(days.reduce((a, d) => a + d.runs, 0)).toBe(3);
  });

  it("offers the same numbers as a table, and an honest empty state", async () => {
    const at = new Date().toISOString();
    renderWith(<FindingsChart runs={[run(at, { critical: 2, high: 1 })]} />, mockClient());
    await userEvent.click(screen.getByRole("radio", { name: "Table" }));
    const table = screen.getByRole("table");
    const row = within(table).getAllByRole("row")[1]!;
    expect(within(row).getAllByRole("cell").map((c) => c.textContent)).toEqual(["2", "1", "0", "0", "1"]);

    renderWith(<FindingsChart runs={[]} />, mockClient());
    expect(screen.getByText("No analyses finished in the last 30 days.")).toBeTruthy();
  });
});

describe("stat cards", () => {
  it("shows plain zero states instead of placeholder numbers", () => {
    renderWith(
      <StatCards
        summary={{ active: 1, archived: 0, designs: 0, imports_7d: 0, analyses_7d: 0 }}
        findings={{ items: [], total: 0, limit: 1, offset: 0, by_severity: {}, designs_analysed: 0 }}
        revisions={0}
        lastRun={null}
      />,
      mockClient(),
    );
    expect(screen.getByText("run an analysis to see findings")).toBeTruthy();
    expect(screen.getByText("no analyses yet")).toBeTruthy();
    expect(screen.getByText("+0 in the last 7 days")).toBeTruthy();
  });
});
