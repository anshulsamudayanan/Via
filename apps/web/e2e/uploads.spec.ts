import { readFileSync } from "node:fs";

import { expect, test } from "@playwright/test";

import { chooseFile, createProject, REFERENCE_BOARD, register, uniqueEmail } from "./helpers";

test("invalid and duplicate uploads are rejected with a clear message", async ({ page }) => {
  await register(page, "Uploader", uniqueEmail("upload"));
  const projectUrl = await createProject(page, "Upload checks");

  // Wrong extension: refused in the browser before anything is sent.
  await chooseFile(page, projectUrl, { name: "notes.txt", mimeType: "text/plain", buffer: Buffer.from("hello") });
  await expect(page.getByText("Couldn't upload notes.txt")).toBeVisible();
  await expect(page.getByText(/Unsupported file type/)).toBeVisible();

  // Right extension, wrong content: refused by the server's content check.
  await chooseFile(page, projectUrl, {
    name: "fake.kicad_pcb",
    mimeType: "application/octet-stream",
    buffer: Buffer.from("MZ\x90\x00 this is not a KiCad board"),
  });
  await expect(page.getByText("Couldn't upload fake.kicad_pcb")).toBeVisible();
  await expect(page.getByText(/This isn't a supported PCB file/)).toBeVisible();

  // Valid file, then the same bytes again: duplicate detected, with a link to the existing design.
  await chooseFile(page, projectUrl, REFERENCE_BOARD);
  await expect(page.getByRole("link", { name: "Open design" })).toBeVisible({ timeout: 60_000 });
  await chooseFile(page, projectUrl, {
    name: "copy.kicad_pcb",
    mimeType: "application/octet-stream",
    buffer: readFileSync(REFERENCE_BOARD),
  });
  await expect(page.getByText("Couldn't upload copy.kicad_pcb")).toBeVisible();
  await expect(page.getByRole("link", { name: /^Open / })).toBeVisible();

  // A file that passes the content check but isn't a valid board fails in the parser, visibly.
  await chooseFile(page, projectUrl, {
    name: "broken.kicad_pcb",
    mimeType: "application/octet-stream",
    buffer: Buffer.from('(kicad_pcb (version 20240108) (generator "pcbnew"'),
  });
  await expect(page.getByText("Parsing failed")).toBeVisible({ timeout: 60_000 });
});
