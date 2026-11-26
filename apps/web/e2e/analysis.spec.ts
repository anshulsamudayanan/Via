import { expect, test } from "@playwright/test";

import { chooseFile, createProject, currentPath, idAfter, REFERENCE_BOARD, register, uniqueEmail } from "./helpers";

type Run = { id: string; status: string; checks: { check_id: string; status: string; details: Record<string, unknown> }[] };
type Page = { total: number; items: { rule: string; source: string; severity: string; components: string[] }[] };

/**
 * The analysis pipeline against the real stack, including KiCad 9's DRC in the eda service.
 * (The analysis UI arrives in Milestone 7; this drives the API with the signed-in browser session.)
 */
test("analysis runs VIA's checks and KiCad's real DRC on an uploaded board", async ({ page }) => {
  await register(page, "Analyst", uniqueEmail("analysis"));
  const projectUrl = await createProject(page, "Analysis e2e");
  await chooseFile(page, projectUrl, REFERENCE_BOARD);
  await page.getByRole("link", { name: "Open design" }).click({ timeout: 60_000 });
  await page.waitForURL("**/designs/**");
  const designId = idAfter(currentPath(page), "designs");

  const started = await page.request.post(`/api/v1/designs/${designId}/analysis-runs`, {
    data: {},
    headers: { "X-VIA-Request": "1" },
  });
  expect(started.status()).toBe(202);
  const runId = ((await started.json()) as Run).id;

  let run: Run = { id: runId, status: "queued", checks: [] };
  await expect
    .poll(async () => {
      run = (await (await page.request.get(`/api/v1/analysis-runs/${runId}`)).json()) as Run;
      return run.status;
    }, { timeout: 90_000 })
    .toBe("succeeded");

  const drc = run.checks.find((c) => c.check_id === "kicad_drc");
  expect(drc?.status).toBe("ok");
  expect(drc?.details.kicad_version).toBe("9.0.6");

  const kicad = (await (await page.request.get(`/api/v1/analysis-runs/${runId}/findings?source=kicad_drc&limit=50`)).json()) as Page;
  // KiCad 9.0.6 reports 2 shorts, 6 clearance, 3 hole clearance and 4 solder mask bridges on this board.
  expect(kicad.total).toBe(15);
  const shorts = kicad.items.filter((f) => f.rule === "shorting_items");
  expect(shorts).toHaveLength(2);
  expect(shorts.every((f) => f.severity === "critical" && f.components.includes("C1"))).toBe(true);

  const via = (await (await page.request.get(`/api/v1/analysis-runs/${runId}/findings?source=via_deterministic&limit=50`)).json()) as Page;
  expect(via.items.map((f) => f.rule)).toContain("copper_spacing_too_small"); // the same short, seen by VIA's geometry
});
