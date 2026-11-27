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
  latest_analysis: {
    design_id: "d1", design_name: "Motor board", status: "succeeded", at: "2026-11-25T09:30:00Z", finding_count: 21,
    by_severity: { critical: 0, high: 2, medium: 15, low: 4, info: 0 },
  },
});
const sensor = project({ id: "p2", name: "Sensor hub", description: "", design_count: 0, latest_import: null, latest_analysis: null, my_role: "viewer", visibility: "organization" });

beforeEach(() => {
  router.push.mockReset();
  localStorage.clear();
});

const dashboardClient = (extra: Parameters<typeof mockClient>[0] = {}) =>
  mockClient({
    projects: { summary: vi.fn().mockResolvedValue(summary()), list: vi.fn().mockResolvedValue(page([motor, sensor], 2)) },
    activity: { list: vi.fn().mockResolvedValue(page([event("auth.login_succeeded"), event("analysis.completed", { revision: 3, findings: 21 })])) },
    ...extra,
  });

describe("Dashboard", () => {
  it("shows real counts, each project's last revision, findings by severity and access, and engineering activity only", async () => {
    renderWith(<DashboardPage />, dashboardClient());

    expect(await screen.findByText(/2 active projects · 3 PCB designs · 5 analyses in the last 7 days/)).toBeTruthy();
    const overview = screen.getByRole("list", { name: "Overview" });
    expect(within(overview).getByText("Revisions")).toBeTruthy();
    expect(within(overview).getByText("+4 in the last 7 days")).toBeTruthy();

    const table = await screen.findByRole("table");
    const row = within(table).getByRole("link", { name: "Motor Controller" }).closest("tr")!;
    expect(within(row).getByRole("link", { name: /Motor board\s*r3/ }).getAttribute("href")).toBe("/projects/p1/designs/d1");
    const findings = within(row).getByRole("link", { name: /2 high, 15 medium, 4 low/ });
    expect(findings.getAttribute("href")).toBe("/projects/p1/designs/d1?tab=analysis");
    expect(within(findings).queryByText("critical")).toBeNull();
    expect(within(row).getByText("Private")).toBeTruthy();

    const empty = within(table).getByRole("link", { name: "Sensor hub" }).closest("tr")!;
    expect(within(empty).getByText("No uploads")).toBeTruthy();
    expect(within(empty).getByText("Not analysed")).toBeTruthy();
    expect(within(empty).getByText("Organization")).toBeTruthy();
    expect(within(empty).getByText(/Viewer/)).toBeTruthy();

    expect(await screen.findByText(/completed an analysis \(r3\): 21 findings/)).toBeTruthy();
    expect(screen.queryByText(/signed in/)).toBeNull();
  });

  it("shows only the total for runs stored before severity counts, and says when there are none", async () => {
    const old = project({ id: "p3", name: "Old run", latest_analysis: { design_id: "d3", design_name: "B", status: "succeeded", at: "2026-11-25T09:30:00Z", finding_count: 7 } });
    const clean = project({ id: "p4", name: "Clean", latest_analysis: { design_id: "d4", design_name: "C", status: "succeeded", at: "2026-11-25T09:30:00Z", finding_count: 0, by_severity: {} } });
    renderWith(<DashboardPage />, dashboardClient({ projects: { summary: vi.fn().mockResolvedValue(summary()), list: vi.fn().mockResolvedValue(page([old, clean])) } }));
    const table = await screen.findByRole("table");
    expect(within(table).getByRole("link", { name: /^7 findings/ })).toBeTruthy();
    expect(within(table).getByRole("link", { name: /^No findings/ })).toBeTruthy();
  });

  it("switches between table and cards and remembers the choice", async () => {
    renderWith(<DashboardPage />, dashboardClient());
    await screen.findByRole("table");
    await userEvent.click(screen.getByRole("radio", { name: "Cards" }));
    expect(screen.queryByRole("table")).toBeNull();
    expect(screen.getByRole("radio", { name: "Cards" }).getAttribute("aria-checked")).toBe("true");
    expect(localStorage.getItem("via-dashboard-view")).toBe("cards");
    expect(screen.getAllByRole("link", { name: /2 high, 15 medium, 4 low/ }).length).toBeGreaterThan(0);
  });

  it("filters on the server (debounced), focuses the filter with /, and sorts", async () => {
    const list = vi.fn().mockResolvedValue(page([motor]));
    renderWith(<DashboardPage />, dashboardClient({ projects: { summary: vi.fn().mockResolvedValue(summary()), list } }));
    await screen.findByRole("table");

    fireEvent.keyDown(document.body, { key: "/" });
    const filter = screen.getByPlaceholderText("Filter projects");
    expect(document.activeElement).toBe(filter);
    fireEvent.change(filter, { target: { value: "motor" } });
    await waitFor(() => expect(list).toHaveBeenLastCalledWith(expect.objectContaining({ q: "motor", status: "active" }), expect.anything()));

    await userEvent.selectOptions(screen.getByRole("combobox", { name: /Sort/ }), "name");
    await waitFor(() => expect(list).toHaveBeenLastCalledWith(expect.objectContaining({ sort: "name" }), expect.anything()));
    expect(screen.getByRole("columnheader", { name: /Project/ }).getAttribute("aria-sort")).toBe("ascending");
  });

  it("uploads a dropped board to a project you can edit, with progress, then toasts a link", async () => {
    let finish!: (v: unknown) => void;
    const upload = vi.fn().mockImplementation((opts: { onProgress: (l: number, t: number) => void }) => {
      opts.onProgress(5, 10);
      return new Promise((r) => (finish = r));
    });
    const client = dashboardClient();
    client.pcb.upload = upload;
    renderWith(<DashboardPage />, client);
    const zone = await screen.findByRole("button", { name: /Upload a KiCad board/ });
    // Viewer-only projects are not offered as targets.
    const target = screen.getByRole("combobox", { name: "Upload to" });
    expect(within(target).queryByText("Sensor hub")).toBeNull();

    const file = new File(["(kicad_pcb)"], "motor.kicad_pcb");
    fireEvent.drop(zone, { dataTransfer: { files: [file], items: [] } });
    await waitFor(() => expect(upload).toHaveBeenCalledWith(expect.objectContaining({ projectId: "p1", file })));
    expect((await screen.findByRole("progressbar", { name: "Upload progress" })).getAttribute("aria-valuenow")).toBe("50");

    finish({ design: { id: "d9", name: "motor" }, revision: { revision_number: 1 } });
    expect((await screen.findByText("Board uploaded")).closest("[role=status]")).toBeTruthy();
    expect(screen.getAllByRole("link", { name: "Open design" })[0]!.getAttribute("href")).toBe("/projects/p1/designs/d9");
  });

  it("rejects an unsupported file before uploading it", async () => {
    const client = dashboardClient();
    renderWith(<DashboardPage />, client);
    const zone = await screen.findByRole("button", { name: /Upload a KiCad board/ });
    fireEvent.drop(zone, { dataTransfer: { files: [new File(["x"], "notes.txt")], items: [] } });
    expect((await screen.findAllByText(/Unsupported file type/)).length).toBeGreaterThan(0);
    expect(client.pcb.upload).not.toHaveBeenCalled();
  });

  it("offers a first step to a new account instead of empty tables", async () => {
    const client = mockClient({ projects: { summary: vi.fn().mockResolvedValue(summary({ active: 0, archived: 0, designs: 0 })), list: vi.fn().mockResolvedValue(page([])) } });
    renderWith(<DashboardPage />, client);
    expect(await screen.findByRole("heading", { name: "Start with a board." })).toBeTruthy();
    expect(screen.getAllByRole("button", { name: "New project" }).length).toBeGreaterThan(0);
    expect(screen.queryByRole("table")).toBeNull();
    expect(screen.queryByRole("list", { name: "Overview" })).toBeNull();
    expect(screen.queryByRole("button", { name: /Upload board/ })).toBeNull();
  });

  it("explains a failed load and retries", async () => {
    const summaryFn = vi.fn().mockRejectedValueOnce(new ApiError(500, "internal_error", "The server had a problem.")).mockResolvedValue(summary());
    const client = mockClient({ projects: { summary: summaryFn, list: vi.fn().mockResolvedValue(page([motor])) } });
    renderWith(<DashboardPage />, client);
    const alert = await screen.findByRole("alert");
    expect(alert.textContent).toContain("Couldn't load the overview");
    await userEvent.click(within(alert).getByRole("button", { name: "Retry" }));
    await waitFor(() => expect(screen.queryByText("Couldn't load the overview")).toBeNull());
    // The page and the sidebar both read the summary: the retry is one more call.
    expect(summaryFn.mock.calls.length).toBeGreaterThanOrEqual(2);
  });
});

describe("AppShell", () => {
  it("marks the current page and links every section", () => {
    navigation.pathname = "/projects/p1";
    renderWith(<AppShell>content</AppShell>, mockClient());
    const nav = screen.getAllByRole("navigation", { name: "Main" })[0]!;
    expect(within(nav).getByRole("link", { name: "Projects" }).getAttribute("aria-current")).toBe("page");
    expect(within(nav).getByRole("link", { name: "Dashboard" }).getAttribute("aria-current")).toBeNull();
    for (const [name, href] of [["Designs", "/designs"], ["Analysis", "/analysis"], ["Components", "/components"]]) {
      expect(within(nav).getByRole("link", { name }).getAttribute("href")).toBe(href);
    }
    expect(within(nav).queryByText("Soon")).toBeNull();
  });

  it("shows the real readiness status and links to the status page", async () => {
    const ready = vi.fn().mockResolvedValue({ status: "error", version: "t", checks: {} });
    renderWith(<AppShell>content</AppShell>, mockClient({ health: { ready } }));
    const link = (await screen.findAllByRole("link", { name: /Degraded service/ }))[0]!;
    expect(link.getAttribute("href")).toBe("/status");
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
