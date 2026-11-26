import { expect, test } from "@playwright/test";

import { register, uniqueEmail } from "./helpers";

test("dashboard: real counts, search, sidebar collapse, theme and mobile navigation", async ({ page }) => {
  await register(page, "Dash Tester", uniqueEmail("dash"));
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

  // Collapse persists across reloads; unbuilt sections are disabled, not links.
  await page.getByRole("button", { name: "Collapse sidebar" }).click();
  await page.reload();
  await expect(page.getByRole("button", { name: "Expand sidebar" })).toBeVisible();
  await page.getByRole("button", { name: "Expand sidebar" }).click();
  await expect(page.getByRole("link", { name: "Designs (coming soon)" })).toHaveAttribute("aria-disabled", "true");

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
});
