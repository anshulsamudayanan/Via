import { defineConfig, devices } from "@playwright/test";

/**
 * End-to-end tests against a running VIA stack (Docker Compose: web, api, worker,
 * postgres, redis, minio). They do not start servers themselves:
 *
 *   docker compose up -d --build
 *   pnpm --filter @via/web e2e
 *
 * Point them elsewhere with E2E_BASE_URL.
 */
export default defineConfig({
  testDir: "./e2e",
  timeout: 90_000,
  expect: { timeout: 15_000 },
  fullyParallel: true,
  forbidOnly: !!process.env.CI,
  retries: 0,
  workers: process.env.CI ? 2 : undefined,
  reporter: process.env.CI ? [["list"], ["html", { open: "never" }]] : "list",
  use: {
    baseURL: process.env.E2E_BASE_URL ?? "http://localhost:3000",
    trace: "off",
    screenshot: "only-on-failure",
  },
  projects: [{ name: "chromium", use: { ...devices["Desktop Chrome"], viewport: { width: 1440, height: 900 } } }],
});
