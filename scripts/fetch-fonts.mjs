#!/usr/bin/env node
/*
 * Download the Array display font (Indian Type Foundry, ITF Free Font License) into the git-ignored
 * apps/web/public/fonts/array/ folder. The licence allows self-hosting for our own site but not
 * redistribution through a public repository, so the files are fetched at build time and never
 * committed. Each file is the official Fontshare version, checked against its pinned SHA-256.
 *
 * If the download fails (no network), the build carries on and the site falls back to the system
 * display stack; nothing else depends on these files.
 *
 * Usage: node scripts/fetch-fonts.mjs
 */
import { createHash } from "node:crypto";
import { existsSync, mkdirSync, readFileSync, writeFileSync } from "node:fs";
import { dirname, join } from "node:path";
import { fileURLToPath } from "node:url";

const ROOT = join(dirname(fileURLToPath(import.meta.url)), "..");
const DEST = join(ROOT, "apps", "web", "public", "fonts", "array");
const FILES = [
  { name: "Array-Regular.woff2", url: "https://cdn.fontshare.com/wf/4QBZHM3FOPYBI67YBLLWZV6ZYIUQTKEE/RXSUFPNEA6YXGQDMHMP3OODY6UWXRJBM/C6VM2RT4EU2NNT5XZWVYHR7WOIOGM4EU.woff2", sha256: "85104fe27cdf0e211c876606ae1ff885a13412f1c12b6dde2c8f570eb613b8a2" },
  { name: "Array-Semibold.woff2", url: "https://cdn.fontshare.com/wf/CASMZPM4VVUC7LKMFQX5SR6SI2NXI6WK/JAJOL32XMCA7KL72O3CN6EMCO3THGWPV/N2P4YTB27O7OQQY6FVFUL232EUHLL7SR.woff2", sha256: "7774227877df6acb9e5780990a84f8856dfe97ddcbaca2c72ad6440e36d07c74" },
  { name: "Array-Bold.woff2", url: "https://cdn.fontshare.com/wf/UPIFVAOR6LZHAYRMF2C77WE3FN5BLNEC/INIDOMS2AGMFQXDWKOC6LOTPXKPZEIHL/2RWR7WKM4ZCDU656OKUXMQXLJH4H3EJD.woff2", sha256: "d1adfdb98b092efdd376d2d10d98a245d29ca272385be0934fa6e5b96ed03e6f" },
];

const sha = (buf) => createHash("sha256").update(buf).digest("hex");

mkdirSync(DEST, { recursive: true });
let failures = 0;
for (const f of FILES) {
  const path = join(DEST, f.name);
  if (existsSync(path) && sha(readFileSync(path)) === f.sha256) {
    console.log(`ok      ${f.name} (cached)`);
    continue;
  }
  try {
    const res = await fetch(f.url, { signal: AbortSignal.timeout(20_000) });
    if (!res.ok) throw new Error(`HTTP ${res.status}`);
    const buf = Buffer.from(await res.arrayBuffer());
    if (sha(buf) !== f.sha256) throw new Error("checksum mismatch");
    writeFileSync(path, buf);
    console.log(`fetched ${f.name}`);
  } catch (err) {
    failures++;
    console.warn(`skipped ${f.name}: ${err instanceof Error ? err.message : err}`);
  }
}
if (failures) console.warn(`${failures} font file(s) unavailable: the site will use the fallback display font.`);
