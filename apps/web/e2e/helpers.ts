import path from "node:path";
import zlib from "node:zlib";

import { expect, type Page } from "@playwright/test";

/** Hand-authored KiCad 8 board (licence: same as this repository); 4 footprints: R1, C1, J1, H1. */
export const REFERENCE_BOARD = path.resolve(
  import.meta.dirname,
  "../../../tests/engineering/fixtures/via_reference_v8.kicad_pcb",
);

export const PASSWORD = "correct horse battery staple";

export function uniqueEmail(prefix: string): string {
  return `${prefix}-${Date.now()}-${Math.random().toString(36).slice(2, 8)}@example.com`;
}

/** The page URL without query string or hash. */
export function currentPath(page: Page): string {
  const url = new URL(page.url());
  return `${url.origin}${url.pathname}`;
}

/** The id that follows `/<segment>/` in a URL. */
export function idAfter(url: string, segment: string): string {
  const match = new RegExp(`/${segment}/([0-9a-f-]{36})`).exec(url);
  if (!match?.[1]) throw new Error(`No ${segment} id in ${url}`);
  return match[1];
}

export async function register(page: Page, name: string, email: string): Promise<void> {
  await page.goto("/register");
  await page.getByLabel("Name").fill(name);
  await page.getByLabel("Email").fill(email);
  await page.getByLabel("Password").fill(PASSWORD);
  await page.getByRole("button", { name: "Create account" }).click();
  await page.waitForURL("**/dashboard");
}

export async function signIn(page: Page, email: string): Promise<void> {
  await page.goto("/login");
  await page.getByLabel("Email").fill(email);
  await page.getByLabel("Password").fill(PASSWORD);
  await page.getByRole("button", { name: "Sign in" }).click();
  await page.waitForURL("**/dashboard");
}

export async function signOut(page: Page): Promise<void> {
  await page.getByRole("button", { name: "Account menu" }).click();
  await page.getByRole("menuitem", { name: "Sign out" }).click();
  await page.waitForURL("**/login**");
}

/** Creates a project from the dashboard and returns its URL (without query string). */
export async function createProject(page: Page, name: string): Promise<string> {
  await page.goto("/dashboard");
  await page.getByRole("button", { name: "New project" }).first().click();
  const dialog = page.getByRole("dialog");
  await dialog.getByLabel("Name").fill(name);
  await dialog.getByRole("button", { name: "Create project" }).click();
  await page.waitForURL("**/projects/**");
  await expect(page.getByRole("heading", { name, level: 1 })).toBeVisible();
  return currentPath(page);
}

/** Uploads a file on the project's PCB Designs tab. */
export async function chooseFile(
  page: Page,
  projectUrl: string,
  file: string | { name: string; mimeType: string; buffer: Buffer },
): Promise<void> {
  await page.goto(`${projectUrl}?tab=designs`);
  await page.getByLabel("Choose a PCB file").setInputFiles(file);
}

/** A minimal ZIP writer (stored, no compression) so tests can build KiCad project archives. */
export function makeZip(files: Record<string, Buffer | string>): Buffer {
  const locals: Buffer[] = [];
  const centrals: Buffer[] = [];
  let offset = 0;
  for (const [name, content] of Object.entries(files)) {
    const data = Buffer.isBuffer(content) ? content : Buffer.from(content);
    const nameBuf = Buffer.from(name);
    const crc = zlib.crc32(data);
    const local = Buffer.alloc(30);
    local.writeUInt32LE(0x04034b50, 0);
    local.writeUInt16LE(20, 4);
    local.writeUInt32LE(crc, 14);
    local.writeUInt32LE(data.length, 18);
    local.writeUInt32LE(data.length, 22);
    local.writeUInt16LE(nameBuf.length, 26);
    const central = Buffer.alloc(46);
    central.writeUInt32LE(0x02014b50, 0);
    central.writeUInt16LE(20, 4);
    central.writeUInt16LE(20, 6);
    central.writeUInt32LE(crc, 16);
    central.writeUInt32LE(data.length, 20);
    central.writeUInt32LE(data.length, 24);
    central.writeUInt16LE(nameBuf.length, 28);
    central.writeUInt32LE(offset, 42);
    locals.push(local, nameBuf, data);
    centrals.push(central, nameBuf);
    offset += local.length + nameBuf.length + data.length;
  }
  const centralDir = Buffer.concat(centrals);
  const end = Buffer.alloc(22);
  end.writeUInt32LE(0x06054b50, 0);
  end.writeUInt16LE(Object.keys(files).length, 8);
  end.writeUInt16LE(Object.keys(files).length, 10);
  end.writeUInt32LE(centralDir.length, 12);
  end.writeUInt32LE(offset, 16);
  return Buffer.concat([...locals, centralDir, end]);
}
