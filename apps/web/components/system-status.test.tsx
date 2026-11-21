import { ApiError } from "@via/api-client";
import type { ReadinessResponse } from "@via/types";
import { cleanup, render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import { SystemStatus } from "./system-status";

afterEach(cleanup);

const healthy: ReadinessResponse = {
  status: "ok",
  version: "0.1.0",
  checks: {
    database: { status: "ok", latency_ms: 4.2, detail: "migrations at 0001" },
    redis: { status: "ok", latency_ms: 1.1, detail: null },
    storage: { status: "ok", latency_ms: 8.9, detail: "s3" },
  },
};

function client(ready: () => Promise<ReadinessResponse>) {
  return { health: { live: vi.fn(), ready: vi.fn(ready) } };
}

describe("SystemStatus", () => {
  it("shows every dependency as operational when healthy", async () => {
    render(<SystemStatus client={client(async () => healthy)} pollMs={0} />);
    expect(await screen.findByText("All systems operational")).toBeTruthy();
    expect(screen.getAllByText("Operational")).toHaveLength(3);
    expect(screen.getByText("migrations at 0001")).toBeTruthy();
    expect(screen.getByText("API v0.1.0")).toBeTruthy();
  });

  it("names the failing dependency when degraded", async () => {
    const degraded: ReadinessResponse = {
      ...healthy,
      status: "error",
      checks: { ...healthy.checks, redis: { status: "error", latency_ms: 500, detail: "ConnectionError" } },
    };
    render(<SystemStatus client={client(async () => degraded)} pollMs={0} />);
    expect(await screen.findByText("Degraded: Redis unavailable")).toBeTruthy();
    expect(screen.getByText("Unavailable")).toBeTruthy();
  });

  it("shows an actionable error when the API cannot be reached", async () => {
    const c = client(async () => {
      throw new ApiError(0, "network_error", "Could not reach the VIA API.");
    });
    render(<SystemStatus client={c} pollMs={0} />);
    expect((await screen.findByRole("alert")).textContent).toContain("The VIA API is not reachable");
    expect(screen.getAllByText("Unknown")).toHaveLength(3);
  });

  it("compact mode renders a one-line summary", async () => {
    render(<SystemStatus client={client(async () => healthy)} pollMs={0} compact />);
    expect(await screen.findByText("All systems operational")).toBeTruthy();
    expect(screen.queryByRole("table")).toBeNull();
  });
});
