import fs from "node:fs";

import { expect, test } from "@playwright/test";

import { REFERENCE_BOARD, register, uniqueEmail } from "./helpers";

const H = { "X-VIA-Request": "1" };

test("designs page lists boards across projects with filters", async ({ page }) => {
  await register(page, "Designs Tester", uniqueEmail("designs"));
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
});
