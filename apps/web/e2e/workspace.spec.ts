import path from "node:path";

import { expect, test } from "@playwright/test";

import { chooseFile, createProject, register, uniqueEmail } from "./helpers";

/** A two-resistor board with an oversized outline and a 0.1 mm track (written by tests/engineering/synthetic.py). */
const OVERSIZED = path.resolve(import.meta.dirname, "fixtures/oversized_outline.kicad_pcb");

/**
 * The Stage 2 workspace through the UI, against the real stack:
 * analyse → inspect a finding on the board → optimize → accept → change set → apply (patched file,
 * new revision) → compare → roll back.
 */
test("analyse, optimize, apply a change set and roll it back", async ({ page }) => {
  test.setTimeout(240_000);
  await register(page, "Workspace", uniqueEmail("workspace"));
  const projectUrl = await createProject(page, "Workspace e2e");
  await chooseFile(page, projectUrl, OVERSIZED);
  await page.getByRole("link", { name: "Open design" }).click({ timeout: 60_000 });
  await page.waitForURL("**/designs/**");
  await expect(page.getByRole("img", { name: /Board view/ })).toBeVisible({ timeout: 30_000 });

  // Analysis: run, then open the narrow-track finding; it is labelled with its source and evidence.
  await page.getByRole("link", { name: "Analysis", exact: true }).click();
  await page.getByRole("button", { name: "Run analysis" }).click();
  const narrow = page.getByRole("button", { name: /narrower than 0\.150 mm/ });
  await expect(narrow).toBeVisible({ timeout: 90_000 });
  await narrow.click();
  const detail = page.getByLabel("Finding details");
  await expect(detail).toContainText("VIA check");
  await expect(detail).toContainText("Evidence (measured)");
  await expect(page.getByRole("button", { name: "Clear highlight" })).toBeVisible();

  // Optimize: generate candidates, accept both validated ones, create a change set.
  await page.getByRole("link", { name: "Optimize", exact: true }).click();
  await page.getByRole("button", { name: "Generate candidates" }).click();
  for (const title of ["Fit the board outline to its content", "Widen tracks below 0.15 mm"]) {
    const toggle = page.getByRole("button", { name: new RegExp(title) });
    await expect(toggle).toBeVisible({ timeout: 90_000 });
    await toggle.click();
    await page.getByRole("button", { name: "Accept", exact: true }).click();
    await expect(toggle).toContainText("accepted");
    await toggle.click(); // collapse
  }
  await page.getByRole("button", { name: /Create change set \(2\)/ }).click();
  await page.waitForURL("**tab=changes**");

  // Apply: the worker patches the original file, verifies it and imports revision 2.
  const card = page.getByLabel(/^Change set /);
  await card.getByRole("button", { name: "Apply" }).click();
  await expect(card).toContainText("Applied", { timeout: 120_000 });
  await expect(card.getByRole("link", { name: /Download file/ })).toBeVisible();
  await expect(card.getByLabel("Revision comparison")).toContainText("Revision 1 → 2");
  // The follow-up analysis on revision 2: the narrow track and the empty margins are resolved, nothing new.
  await expect
    .poll(async () => {
      await page.reload();
      return (await page.getByLabel("Revision comparison").textContent()) ?? "";
    }, { timeout: 90_000 })
    .toMatch(/2 resolved, 0 introduced/);
  const comparison = page.getByLabel("Revision comparison");
  await expect(comparison).toContainText("Tracks on A are narrower than 0.150 mm");
  await expect(comparison).toContainText("Board has large empty margins");

  const download = await Promise.all([page.waitForEvent("download"), page.getByRole("link", { name: /Download file/ }).click()]);
  expect(download[0].suggestedFilename()).toMatch(/-via-r2\.kicad_pcb$/);

  // Roll back: revision 1 is current again and revision 2 stays in the history.
  await page.getByRole("button", { name: "Roll back" }).click();
  await expect(page.getByLabel(/^Change set /)).toContainText("Rolled back");
  await page.getByRole("link", { name: "Revisions", exact: true }).click();
  await expect(page.getByText(/from rev 1 by a change set/)).toBeVisible();
});
