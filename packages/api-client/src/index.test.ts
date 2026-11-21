import { describe, expect, it, vi } from "vitest";

import { ApiError, createViaClient } from "./index";

function jsonResponse(status: number, body: unknown, headers: Record<string, string> = {}) {
  return new Response(JSON.stringify(body), { status, headers: { "content-type": "application/json", ...headers } });
}

describe("createViaClient", () => {
  it("returns typed data for 2xx responses", async () => {
    const fetch = vi.fn().mockResolvedValue(jsonResponse(200, { status: "ok", version: "0.1.0" }));
    const client = createViaClient({ fetch });
    await expect(client.health.live()).resolves.toEqual({ status: "ok", version: "0.1.0" });
    expect(fetch).toHaveBeenCalledWith(
      "/api/v1/health",
      expect.objectContaining({ method: "GET", credentials: "same-origin" }),
    );
  });

  it("treats readiness 503 as data, not an error", async () => {
    const body = { status: "error", version: "0.1.0", checks: { redis: { status: "error", latency_ms: 1, detail: "x" } } };
    const client = createViaClient({ fetch: vi.fn().mockResolvedValue(jsonResponse(503, body)) });
    await expect(client.health.ready()).resolves.toEqual(body);
  });

  it("maps the API error envelope to ApiError", async () => {
    const envelope = { error: { code: "not_found", message: "Project not found", details: null, request_id: "r-1" } };
    const client = createViaClient({ fetch: vi.fn().mockResolvedValue(jsonResponse(404, envelope)) });
    const err = await client.request("/api/v1/projects/x").catch((e: unknown) => e);
    expect(err).toBeInstanceOf(ApiError);
    expect(err).toMatchObject({ status: 404, code: "not_found", message: "Project not found", requestId: "r-1" });
  });

  it("reports network failures with a friendly message", async () => {
    const client = createViaClient({ fetch: vi.fn().mockRejectedValue(new TypeError("fetch failed")) });
    const err = (await client.health.live().catch((e: unknown) => e)) as ApiError;
    expect(err.isNetworkError).toBe(true);
    expect(err.code).toBe("network_error");
  });

  it("handles non-JSON error bodies (e.g. proxy errors)", async () => {
    const fetch = vi.fn().mockResolvedValue(new Response("<html>Bad Gateway</html>", { status: 502, headers: { "x-request-id": "abc" } }));
    const err = (await createViaClient({ fetch }).health.live().catch((e: unknown) => e)) as ApiError;
    expect(err).toMatchObject({ status: 502, code: "http_error", requestId: "abc" });
  });

  it("sends the CSRF header and JSON body on unsafe methods only", async () => {
    const fetch = vi.fn().mockImplementation(async () => jsonResponse(200, {}));
    const client = createViaClient({ fetch, baseUrl: "http://api.test/" });
    await client.request("/api/v1/things", { method: "POST", body: { a: 1 } });
    await client.request("/api/v1/things");
    const [postUrl, postInit] = fetch.mock.calls[0]!;
    const [, getInit] = fetch.mock.calls[1]!;
    expect(postUrl).toBe("http://api.test/api/v1/things");
    expect(postInit.headers["X-VIA-Request"]).toBe("1");
    expect(postInit.body).toBe('{"a":1}');
    expect(getInit.headers["X-VIA-Request"]).toBeUndefined();
  });

  it("propagates aborts unchanged", async () => {
    const abort = new DOMException("aborted", "AbortError");
    const client = createViaClient({ fetch: vi.fn().mockRejectedValue(abort) });
    await expect(client.health.live()).rejects.toBe(abort);
  });
});

describe("resource methods", () => {
  it("builds query strings, skipping empty values, and encodes ids", async () => {
    const fetch = vi.fn().mockImplementation(async () => jsonResponse(200, { items: [], total: 0, limit: 25, offset: 0 }));
    const client = createViaClient({ fetch });
    await client.projects.list({ q: "motor driver", status: "all", sort: undefined, offset: 0 });
    expect(fetch.mock.calls[0]![0]).toBe("/api/v1/projects?q=motor+driver&status=all&offset=0");
    await client.projects.get("a/b");
    expect(fetch.mock.calls[1]![0]).toBe("/api/v1/projects/a%2Fb");
  });

  it("returns undefined for 204 No Content", async () => {
    const fetch = vi.fn().mockResolvedValue(new Response(null, { status: 204 }));
    await expect(createViaClient({ fetch }).projects.delete("p1")).resolves.toBeUndefined();
    expect(fetch.mock.calls[0]![1].method).toBe("DELETE");
    expect(fetch.mock.calls[0]![1].headers["X-VIA-Request"]).toBe("1");
  });
});
