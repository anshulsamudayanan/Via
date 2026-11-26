import fs from "node:fs";

import { expect, test } from "@playwright/test";

import { REFERENCE_BOARD, register, uniqueEmail } from "./helpers";

const H = { "X-VIA-Request": "1" };

// One account for every sidebar page: registration is rate limited per IP (10/hour), and the
// whole e2e suite must stay under it.
test("sidebar pages: dashboard, designs, analysis and components", async ({ page }) => {
  test.setTimeout(300_000);
  await register(page, "Sidebar Tester", uniqueEmail("sidebar"));
  await expect(page.getByRole("heading", { name: "Dashboard" })).toBeVisible();
  // A new account gets a first step, not empty tables.
  await expect(page.getByText("Get started")).toBeVisible();

  const created = await page.request.post("/api/v1/projects", { headers: { "X-VIA-Request": "1" }, data: { name: "Dash board project" } });
  expect(created.ok()).toBeTruthy();
  await page.reload();
  const overview = page.locator("dl");
  await expect(overview.getByText("Active projects")).toBeVisible();
  await expect(overview.getByText("Active projects").locator("xpath=following-sibling::dd")).toHaveText("1");
  await expect(page.getByRole("table").getByRole("link", { name: "Dash board project" })).toBeVisible();

  // Global search finds the project and opens it.
  await page.keyboard.press("Control+k");
  await page.getByRole("combobox", { name: "Search projects and pages" }).fill("Dash board");
  await expect(page.getByRole("option", { name: /Dash board project/ })).toBeVisible();
  await page.keyboard.press("Enter");
  await expect(page).toHaveURL(/\/projects\/[0-9a-f-]+$/);
  await page.goto("/dashboard");

  // Collapse persists across reloads.
  await page.getByRole("button", { name: "Collapse sidebar" }).click();
  await page.reload();
  await expect(page.getByRole("button", { name: "Expand sidebar" })).toBeVisible();
  await page.getByRole("button", { name: "Expand sidebar" }).click();

  // Theme switch.
  const theme = await page.locator("html").getAttribute("data-theme");
  await page.getByRole("button", { name: /Switch to (light|dark) theme/ }).first().click();
  await expect(page.locator("html")).not.toHaveAttribute("data-theme", theme ?? "dark");

  // Mobile: a drawer, no horizontal scroll.
  await page.setViewportSize({ width: 390, height: 844 });
  await page.getByRole("button", { name: "Open navigation" }).click();
  await page.getByRole("dialog", { name: "Navigation" }).getByRole("link", { name: "Projects" }).click();
  await expect(page).toHaveURL(/\/projects$/);
  expect(await page.evaluate(() => document.documentElement.scrollWidth - window.innerWidth)).toBeLessThanOrEqual(0);

  // ----- Designs: boards across projects, with filters.
  await page.setViewportSize({ width: 1280, height: 800 });
  const board = fs.readFileSync(REFERENCE_BOARD);
  for (const name of ["Alpha project", "Beta project"]) {
    const project = await (await page.request.post("/api/v1/projects", { headers: H, data: { name } })).json();
    const resp = await page.request.post("/api/v1/pcb/import", {
      headers: H,
      multipart: { project_id: project.id, file: { name: `${name.split(" ")[0]!.toLowerCase()}.kicad_pcb`, mimeType: "application/octet-stream", buffer: board } },
    });
    expect(resp.status()).toBe(202);
  }

  await page.getByRole("navigation", { name: "Main" }).getByRole("link", { name: "Designs" }).click();
  await expect(page).toHaveURL(/\/designs$/);
  await expect(page.getByRole("heading", { name: "Designs" })).toBeVisible();
  const table = page.getByRole("table");
  await expect(table.getByRole("link", { name: "alpha", exact: true })).toBeVisible();
  await expect(table.getByRole("link", { name: "beta", exact: true })).toBeVisible();
  await expect(table.getByText("Imported").first()).toBeVisible({ timeout: 60_000 });

  await page.getByRole("searchbox", { name: "Search designs" }).fill("beta");
  await expect(page).toHaveURL(/q=beta/);
  await expect(table.getByRole("link", { name: "alpha", exact: true })).toHaveCount(0);
  await expect(table.getByRole("link", { name: "beta", exact: true })).toBeVisible();

  await page.getByRole("button", { name: "Failed" }).click();
  await expect(page.getByText("No matching designs")).toBeVisible();

  await page.goto("/designs");
  await table.getByRole("link", { name: "alpha", exact: true }).click();
  await expect(page).toHaveURL(/\/projects\/[0-9a-f-]+\/designs\/[0-9a-f-]+$/);

  // ----- Analysis and Components.
  const project = await (await page.request.post("/api/v1/projects", { headers: H, data: { name: "Cross project" } })).json();
  const imported = await (
    await page.request.post("/api/v1/pcb/import", {
      headers: H,
      multipart: { project_id: project.id, file: { name: "cross.kicad_pcb", mimeType: "application/octet-stream", buffer: fs.readFileSync(REFERENCE_BOARD) } },
    })
  ).json();
  await expect
    .poll(async () => (await (await page.request.get(`/api/v1/revisions/${imported.revision.id}`)).json()).status, { timeout: 60_000 })
    .toBe("ready");
  const run = await (await page.request.post(`/api/v1/designs/${imported.design.id}/analysis-runs`, { headers: H, data: {} })).json();
  await expect
    .poll(async () => (await (await page.request.get(`/api/v1/analysis-runs/${run.id}`)).json()).status, { timeout: 120_000 })
    .toMatch(/succeeded|failed/);

  // Analysis: findings from the latest run, each linking to the finding in its design.
  await page.getByRole("navigation", { name: "Main" }).getByRole("link", { name: "Analysis" }).click();
  await expect(page.getByRole("heading", { name: "Analysis" })).toBeVisible();
  await expect(page.getByText("latest analysis of 1 design")).toBeVisible();
  const findings = page.getByRole("list", { name: "Findings" });
  const first = findings.getByRole("link").first();
  await expect(first).toBeVisible();
  const title = (await first.locator("p").first().textContent())!;
  await first.click();
  await expect(page).toHaveURL(/tab=analysis.*finding=/);
  await expect(page.getByLabel("Finding details").getByRole("heading", { name: title })).toBeVisible();

  await page.goto("/analysis?view=runs");
  await expect(page.getByRole("list", { name: "Analysis runs" }).getByRole("link", { name: /^cross r1/ })).toBeVisible();

  // Components: grouped parts, linking into the design's component list.
  await page.goto("/components");
  await expect(page.getByRole("heading", { name: "Components" })).toBeVisible();
  const parts = page.getByRole("table");
  await expect(parts.getByRole("link", { name: "cross" }).first()).toBeVisible();
  await page.getByRole("searchbox", { name: "Search components" }).fill("R1");
  await expect(page).toHaveURL(/q=R1/);
  await parts.getByRole("link", { name: "cross" }).first().click();
  await expect(page).toHaveURL(/tab=components&q=/);
});
