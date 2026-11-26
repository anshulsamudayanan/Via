import { readFileSync } from "node:fs";

import { expect, test } from "@playwright/test";

import { chooseFile, createProject, makeZip, REFERENCE_BOARD, register, uniqueEmail } from "./helpers";

const PROJECT = {
  board: { design_settings: { rules: { min_clearance: 0.15, min_track_width: 0.18 } } },
  net_settings: {
    classes: [
      { name: "Default", clearance: 0.2, track_width: 0.25 },
      { name: "Power", clearance: 0.3, track_width: 0.5 },
    ],
    netclass_patterns: [{ netclass: "Power", pattern: "VCC" }],
  },
};

test("a KiCad project .zip is imported with its design rules", async ({ page }) => {
  await register(page, "Project Importer", uniqueEmail("zip"));
  const projectUrl = await createProject(page, "Zip import");
  const archive = makeZip({
    "ref/ref.kicad_pcb": readFileSync(REFERENCE_BOARD),
    "ref/ref.kicad_pro": JSON.stringify(PROJECT),
  });
  await chooseFile(page, projectUrl, { name: "ref.zip", mimeType: "application/zip", buffer: archive });
  await expect(page.getByText("4 components", { exact: false })).toBeVisible({ timeout: 60_000 });
  await page.getByRole("link", { name: "Open design" }).click();
  await page.waitForURL("**/designs/**");
  await expect(page.getByText("ref/ref.kicad_pcb")).toBeVisible();
  await expect(page.getByText("Project file · 2 net classes")).toBeVisible();
  await expect(page.getByRole("img", { name: /Board view of/ })).toBeVisible();

  // An archive without a board is refused with a clear reason.
  await chooseFile(page, projectUrl, { name: "empty.zip", mimeType: "application/zip", buffer: makeZip({ "notes.txt": "hi" }) });
  await expect(page.getByText("Couldn't upload empty.zip")).toBeVisible();
  await expect(page.getByText(/doesn't contain a \.kicad_pcb board/)).toBeVisible();
});
