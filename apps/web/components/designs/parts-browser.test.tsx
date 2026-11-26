import type { PartListItem } from "@via/types";
import { screen, waitFor, within } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";

import { mockClient, navigation, page, renderWith } from "@/test/helpers";

import { PartsBrowser } from "./parts-browser";

const part = (o: Partial<PartListItem> = {}): PartListItem => ({
  value: "10k", footprint: "Resistor_SMD:R_0603_1608Metric", placements: 14, design_count: 3,
  references: ["R1", "R2", "R10"], references_truncated: true,
  designs: [{ id: "d1", name: "Motor board", project_id: "p1" }], ...o,
});

beforeEach(() => {
  navigation.pathname = "/components";
  navigation.search = new URLSearchParams();
});

describe("PartsBrowser", () => {
  it("lists grouped parts with placements, references and links into each design's components", async () => {
    const parts = vi.fn().mockResolvedValue({ ...page([part(), part({ value: null, footprint: "TestPoint", placements: 1, design_count: 1, references: ["TP1"], references_truncated: false })], 2), placements: 15, designs: 3 });
    renderWith(<PartsBrowser />, mockClient({ components: { parts }, projects: { list: vi.fn().mockResolvedValue(page([])) } }));

    const table = await screen.findByRole("table");
    const row = within(table).getByText("10k").closest("tr")!;
    expect(within(row).getByText("R1, R2, R10, …")).toBeTruthy();
    expect(within(row).getByText("14")).toBeTruthy();
    expect(within(row).getByText("R_0603_1608Metric")).toBeTruthy();
    expect(within(row).getByRole("link", { name: "Motor board" }).getAttribute("href")).toBe("/projects/p1/designs/d1?tab=components&q=10k");
    expect(within(row).getByText("+2 more")).toBeTruthy();
    expect(within(table).getByText("No value")).toBeTruthy();
    expect(parts).toHaveBeenCalledWith(expect.objectContaining({ sort: "placements", include_archived: false }), expect.anything());
  });

  it("passes URL filters to the API", async () => {
    navigation.search = new URLSearchParams("q=0603&sort=footprint&archived=1&page=2");
    const parts = vi.fn().mockResolvedValue({ ...page([]), placements: 0, designs: 0 });
    renderWith(<PartsBrowser />, mockClient({ components: { parts }, projects: { list: vi.fn().mockResolvedValue(page([])) } }));
    await waitFor(() => expect(parts).toHaveBeenCalledWith(expect.objectContaining({ q: "0603", sort: "footprint", include_archived: true, offset: 100 }), expect.anything()));
    expect(await screen.findByText("No matching components")).toBeTruthy();
  });
});
