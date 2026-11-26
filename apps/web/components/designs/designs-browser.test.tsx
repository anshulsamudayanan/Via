import type { DesignListItem, RevisionBrief } from "@via/types";
import { screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, describe, expect, it, vi } from "vitest";

import { mockClient, navigation, page, project, renderWith, router } from "@/test/helpers";

import { DesignsBrowser } from "./designs-browser";

const rev = (o: Partial<RevisionBrief> = {}): RevisionBrief => ({
  id: "r2", revision_number: 2, status: "ready", created_at: "2026-11-25T09:00:00Z",
  object_counts: { component_count: 42, net_count: 17, copper_layer_count: 4 }, ...o,
});

const item = (o: Partial<DesignListItem> = {}): DesignListItem => ({
  id: "d1", name: "Motor board", description: "", project: { id: "p1", name: "Motor Controller" }, my_role: "owner",
  project_archived: false, revision_count: 2, created_at: "2026-11-20T10:00:00Z", updated_at: "2026-11-25T10:00:00Z",
  current_revision: rev(), latest_revision: rev(),
  latest_analysis: { status: "succeeded", at: "2026-11-25T09:30:00Z", revision_number: 2, finding_count: 7 }, ...o,
});

beforeEach(() => {
  navigation.pathname = "/designs";
  navigation.search = new URLSearchParams();
  router.replace.mockReset();
});

describe("DesignsBrowser", () => {
  it("lists designs from every project with their parsed counts, upload and analysis state", async () => {
    const failedUpload = item({
      id: "d2", name: "Sensor board", project: { id: "p2", name: "Sensor hub" }, project_archived: true, revision_count: 3,
      latest_revision: rev({ id: "r3", revision_number: 3, status: "failed" }), latest_analysis: null,
    });
    const browse = vi.fn().mockResolvedValue(page([item(), failedUpload], 2));
    renderWith(<DesignsBrowser />, mockClient({ designs: { browse }, projects: { list: vi.fn().mockResolvedValue(page([project()])) } }));

    const table = await screen.findByRole("table");
    const motor = within(table).getByRole("link", { name: "Motor board" }).closest("tr")!;
    expect(within(table).getByRole("link", { name: "Motor board" }).getAttribute("href")).toBe("/projects/p1/designs/d1");
    expect(within(motor).getByText("42")).toBeTruthy();
    expect(within(motor).getByText("17")).toBeTruthy();
    expect(within(motor).getByRole("link", { name: /7\s*findings/ }).getAttribute("href")).toBe("/projects/p1/designs/d1?tab=analysis");

    const sensor = within(table).getByRole("link", { name: "Sensor board" }).closest("tr")!;
    expect(within(sensor).getByText("Import failed")).toBeTruthy();
    expect(within(sensor).getByText("(showing r2)")).toBeTruthy();
    expect(within(sensor).getByText("Archived")).toBeTruthy();
    expect(within(sensor).getByText("Not analysed")).toBeTruthy();
    expect(browse).toHaveBeenCalledWith(expect.objectContaining({ status: "all", sort: "updated", include_archived: false, offset: 0 }), expect.anything());
  });

  it("reads filters from the URL and writes changes back to it", async () => {
    navigation.search = new URLSearchParams("status=failed&sort=name&q=motor&archived=1&page=1");
    const browse = vi.fn().mockResolvedValue(page([item()], 30));
    renderWith(<DesignsBrowser />, mockClient({ designs: { browse }, projects: { list: vi.fn().mockResolvedValue(page([])) } }));
    await waitFor(() =>
      expect(browse).toHaveBeenCalledWith(
        expect.objectContaining({ q: "motor", status: "failed", sort: "name", include_archived: true, offset: 25 }),
        expect.anything(),
      ),
    );
    expect(screen.getByRole("button", { name: "Failed" }).getAttribute("aria-pressed")).toBe("true");
    await userEvent.click(screen.getByRole("button", { name: "Imported" }));
    expect(router.replace).toHaveBeenLastCalledWith("/designs?status=ready&sort=name&q=motor&archived=1", { scroll: false });
  });

  it("distinguishes no designs at all from no matches", async () => {
    const client = mockClient({ projects: { list: vi.fn().mockResolvedValue(page([])) } });
    const { unmount } = renderWith(<DesignsBrowser />, client);
    expect(await screen.findByText("No designs yet")).toBeTruthy();
    unmount();
    navigation.search = new URLSearchParams("q=zzz");
    renderWith(<DesignsBrowser />, client);
    expect(await screen.findByText("No matching designs")).toBeTruthy();
  });
});
