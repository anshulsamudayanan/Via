import { ApiError } from "@via/api-client";
import { screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it, vi } from "vitest";

import { design, me, mockClient, navigation, page, project, renderWith, router } from "@/test/helpers";

import { NewProjectDialog } from "./projects/new-project-dialog";
import { ProjectsBrowser } from "./projects/projects-browser";
import { ProjectWorkspace } from "./projects/workspace";
import { SessionProvider } from "./session";

describe("SessionProvider (protected routes)", () => {
  it("redirects to login with the current path when the API says 401", async () => {
    navigation.pathname = "/projects/p1";
    const client = mockClient({ auth: { me: vi.fn().mockRejectedValue(new ApiError(401, "unauthorized", "Sign in")) } });
    renderWith(
      <SessionProvider>
        <p>secret content</p>
      </SessionProvider>,
      client,
      false,
    );
    await waitFor(() => expect(router.replace).toHaveBeenCalledWith("/login?next=%2Fprojects%2Fp1"));
    expect(screen.queryByText("secret content")).toBeNull();
  });

  it("renders children once the session is confirmed", async () => {
    const client = mockClient({ auth: { me: vi.fn().mockResolvedValue(me) } });
    renderWith(
      <SessionProvider>
        <p>secret content</p>
      </SessionProvider>,
      client,
      false,
    );
    expect(await screen.findByText("secret content")).toBeTruthy();
  });
});

describe("NewProjectDialog", () => {
  it("creates a private project and reports it", async () => {
    const created = project({ id: "new" });
    const create = vi.fn().mockResolvedValue(created);
    const onCreated = vi.fn();
    renderWith(<NewProjectDialog onCreated={onCreated} />, mockClient({ projects: { create } }));
    const user = userEvent.setup();
    await user.click(screen.getByRole("button", { name: "New project" }));
    const dialog = screen.getByRole("dialog", { name: "New project" });
    await user.click(within(dialog).getByRole("button", { name: "Create project" }));
    expect(within(dialog).getByText("Enter a project name.")).toBeTruthy();
    await user.type(within(dialog).getByLabelText("Name"), "Motor Controller");
    await user.click(within(dialog).getByRole("button", { name: "Create project" }));
    expect(create).toHaveBeenCalledWith({ name: "Motor Controller", description: "", organization_id: "o1", visibility: "private" });
    await waitFor(() => expect(onCreated).toHaveBeenCalledWith(created));
  });
});

describe("ProjectsBrowser", () => {
  it("lists projects from the API", async () => {
    const list = vi.fn().mockResolvedValue(page([project(), project({ id: "p2", name: "Sensor", my_role: "viewer", visibility: "organization" })]));
    renderWith(<ProjectsBrowser />, mockClient({ projects: { list } }));
    expect(await screen.findByRole("link", { name: "Motor Controller" })).toBeTruthy();
    expect(screen.getByRole("link", { name: "Sensor" }).getAttribute("href")).toBe("/projects/p2");
    expect(screen.getByText("1–2 of 2")).toBeTruthy();
    expect(list).toHaveBeenCalledWith({ q: undefined, status: "active", sort: "updated", limit: 25, offset: 0 }, expect.anything());
  });

  it("shows the first-project empty state with no projects", async () => {
    renderWith(<ProjectsBrowser />, mockClient({ projects: { list: vi.fn().mockResolvedValue(page([])) } }));
    expect(await screen.findByText("No projects yet")).toBeTruthy();
  });

  it("reads filters from the URL", async () => {
    navigation.search = new URLSearchParams("status=archived&q=motor&sort=name");
    const list = vi.fn().mockResolvedValue(page([]));
    renderWith(<ProjectsBrowser />, mockClient({ projects: { list } }));
    expect(await screen.findByText("No matching projects")).toBeTruthy();
    expect(list).toHaveBeenCalledWith({ q: "motor", status: "archived", sort: "name", limit: 25, offset: 0 }, expect.anything());
  });
});

describe("ProjectWorkspace", () => {
  it("shows project details and each design's latest analysis", async () => {
    navigation.pathname = "/projects/p1";
    navigation.search = new URLSearchParams("tab=analysis");
    renderWith(<ProjectWorkspace />, mockClient({ projects: { get: vi.fn().mockResolvedValue(project()) }, designs: { list: vi.fn().mockResolvedValue([design()]) } }));
    expect(await screen.findByRole("heading", { name: "Motor Controller" })).toBeTruthy();
    expect((await screen.findByRole("link", { name: "Motor board" })).getAttribute("href")).toBe("/projects/p1/designs/d1?tab=analysis");
    expect(await screen.findByText("Not analysed yet")).toBeTruthy();
    expect(screen.queryByText("Coming soon")).toBeNull();
    const nav = screen.getByRole("navigation", { name: "Project sections" });
    expect(within(nav).getAllByRole("link").map((l) => l.textContent)).toEqual([
      "Overview", "PCB Designs", "Files", "Components", "Analysis", "Activity", "Settings",
    ]);
  });

  it("treats inaccessible projects as not found", async () => {
    const get = vi.fn().mockRejectedValue(new ApiError(404, "not_found", "Project not found"));
    renderWith(<ProjectWorkspace />, mockClient({ projects: { get } }));
    expect(await screen.findByText("Project not found")).toBeTruthy();
  });

  it("viewers see read-only settings without the danger zone", async () => {
    navigation.search = new URLSearchParams("tab=settings");
    const client = mockClient({
      projects: {
        get: vi.fn().mockResolvedValue(project({ my_role: "viewer" })),
        members: vi.fn().mockResolvedValue([{ user: { id: "u1", display_name: "Ada Lovelace" }, role: "viewer", added_at: "" }]),
      },
    });
    renderWith(<ProjectWorkspace />, client);
    expect(((await screen.findByLabelText("Project name")) as HTMLInputElement).disabled).toBe(true);
    expect(screen.queryByText("Danger zone")).toBeNull();
    expect(screen.queryByRole("button", { name: "Save changes" })).toBeNull();
  });
});
