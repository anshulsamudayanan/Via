import type { ActivityItem, ProjectSummary } from "@via/types";
import { ApiError } from "@via/api-client";
import { fireEvent, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, describe, expect, it, vi } from "vitest";

import DashboardPage from "@/app/(app)/dashboard/page";
import { AppShell } from "@/components/app-shell";
import { mockClient, navigation, page, project, renderWith, router } from "@/test/helpers";

const summary = (o: Partial<ProjectSummary> = {}): ProjectSummary => ({ active: 2, archived: 1, designs: 3, imports_7d: 4, analyses_7d: 5, ...o });

function event(action: string, details: Record<string, unknown> = {}, extra: Partial<ActivityItem> = {}): ActivityItem {
  return {
    id: `${action}-${Math.random()}`, action, created_at: "2026-11-25T10:00:00Z", actor: { id: "u1", display_name: "Ada Lovelace" },
    project: { id: "p1", name: "Motor Controller" }, target_type: null, target_id: null, details, ...extra,
  };
}

const motor = project({
  design_count: 2,
  latest_import: { design_id: "d1", design_name: "Motor board", revision_number: 3, status: "ready", at: "2026-11-25T09:00:00Z" },
  latest_analysis: { design_id: "d1", design_name: "Motor board", status: "succeeded", at: "2026-11-25T09:30:00Z", finding_count: 21 },
});
const sensor = project({ id: "p2", name: "Sensor hub", description: "", design_count: 0, latest_import: null, latest_analysis: null });

beforeEach(() => {
  router.push.mockReset();
  localStorage.clear();
});

describe("Dashboard", () => {
  it("shows real counts, each project's latest import and analysis, and engineering activity only", async () => {
    const client = mockClient({
      projects: { summary: vi.fn().mockResolvedValue(summary()), list: vi.fn().mockResolvedValue(page([motor, sensor], 2)) },
      activity: { list: vi.fn().mockResolvedValue(page([event("auth.login_succeeded"), event("analysis.completed", { revision: 3, findings: 21 })])) },
    });
    renderWith(<DashboardPage />, client);

    const overview = await screen.findByText("PCB designs");
    expect(within(overview.closest("dl")!).getByText("3")).toBeTruthy();
    expect(screen.getByText("Imports · 7 days").nextElementSibling?.textContent).toBe("4");
    expect(screen.getByText("Analyses · 7 days").nextElementSibling?.textContent).toBe("5");

    const table = await screen.findByRole("table");
    const row = within(table).getByRole("link", { name: "Motor Controller" }).closest("tr")!;
    expect(within(row).getByRole("link", { name: /Imported/ }).getAttribute("href")).toBe("/projects/p1/designs/d1");
    expect(within(row).getByRole("link", { name: /21\s*findings/ }).getAttribute("href")).toBe("/projects/p1/designs/d1?tab=analysis");
    const empty = within(table).getByRole("link", { name: "Sensor hub" }).closest("tr")!;
    expect(within(empty).getByText("No uploads")).toBeTruthy();
    expect(within(empty).getByText("Not analysed")).toBeTruthy();

    expect(await screen.findByText(/completed an analysis \(r3\): 21 findings/)).toBeTruthy();
    expect(screen.queryByText(/signed in/)).toBeNull();
  });

  it("filters on the server (debounced) and sorts", async () => {
    const list = vi.fn().mockResolvedValue(page([motor]));
    const client = mockClient({ projects: { summary: vi.fn().mockResolvedValue(summary()), list } });
    renderWith(<DashboardPage />, client);
    await screen.findByRole("table");

    fireEvent.change(screen.getAllByPlaceholderText("Filter projects")[0]!, { target: { value: "motor" } });
    await waitFor(() => expect(list).toHaveBeenLastCalledWith(expect.objectContaining({ q: "motor", status: "active" }), expect.anything()));

    await userEvent.selectOptions(screen.getByRole("combobox", { name: /Sort/ }), "name");
    await waitFor(() => expect(list).toHaveBeenLastCalledWith(expect.objectContaining({ sort: "name" }), expect.anything()));
    expect(screen.getByRole("columnheader", { name: /Project/ }).getAttribute("aria-sort")).toBe("ascending");
  });

  it("offers a first step to a new account instead of empty tables", async () => {
    const client = mockClient({ projects: { summary: vi.fn().mockResolvedValue(summary({ active: 0, archived: 0, designs: 0 })), list: vi.fn().mockResolvedValue(page([])) } });
    renderWith(<DashboardPage />, client);
    expect(await screen.findByText("Get started")).toBeTruthy();
    expect(screen.queryByRole("table")).toBeNull();
    expect(screen.queryByText("PCB designs")).toBeNull();
  });

  it("explains a failed load and retries", async () => {
    const summaryFn = vi.fn().mockRejectedValueOnce(new ApiError(500, "internal_error", "The server had a problem.")).mockResolvedValue(summary());
    const client = mockClient({ projects: { summary: summaryFn, list: vi.fn().mockResolvedValue(page([motor])) } });
    renderWith(<DashboardPage />, client);
    const alert = await screen.findByRole("alert");
    expect(alert.textContent).toContain("Couldn't load the overview");
    await userEvent.click(within(alert).getByRole("button", { name: "Retry" }));
    expect(await screen.findByText("PCB designs")).toBeTruthy();
    expect(summaryFn).toHaveBeenCalledTimes(2);
  });
});

describe("AppShell", () => {
  it("marks the current page, and shows unbuilt sections as disabled, not as links", () => {
    navigation.pathname = "/projects/p1";
    renderWith(<AppShell>content</AppShell>, mockClient());
    const nav = screen.getAllByRole("navigation", { name: "Main" })[0]!;
    expect(within(nav).getByRole("link", { name: "Projects" }).getAttribute("aria-current")).toBe("page");
    expect(within(nav).getByRole("link", { name: "Dashboard" }).getAttribute("aria-current")).toBeNull();
    const designs = within(nav).getByRole("link", { name: "Designs (coming soon)" });
    expect(designs.getAttribute("aria-disabled")).toBe("true");
    expect(designs.getAttribute("href")).toBeNull();
  });

  it("collapses the sidebar and remembers it", async () => {
    renderWith(<AppShell>content</AppShell>, mockClient());
    await userEvent.click(screen.getByRole("button", { name: "Collapse sidebar" }));
    expect(screen.getByRole("button", { name: "Expand sidebar" }).getAttribute("aria-expanded")).toBe("false");
    expect(localStorage.getItem("via-sidebar-collapsed")).toBe("1");
    await userEvent.click(screen.getByRole("button", { name: "Expand sidebar" }));
    expect(localStorage.getItem("via-sidebar-collapsed")).toBe("0");
  });

  it("opens search with Ctrl+K, finds projects on the server and opens one with Enter", async () => {
    const list = vi.fn().mockResolvedValue(page([motor]));
    renderWith(<AppShell>content</AppShell>, mockClient({ projects: { list } }));
    fireEvent.keyDown(window, { key: "k", ctrlKey: true });
    const input = await screen.findByRole("combobox", { name: "Search projects and pages" });
    await userEvent.type(input, "motor");
    await waitFor(() => expect(list).toHaveBeenLastCalledWith(expect.objectContaining({ q: "motor", status: "all" }), expect.anything()));
    expect(await screen.findByRole("option", { name: /Motor Controller/ })).toBeTruthy();
    await userEvent.keyboard("{Enter}");
    expect(router.push).toHaveBeenCalledWith("/projects/p1");
  });
});
