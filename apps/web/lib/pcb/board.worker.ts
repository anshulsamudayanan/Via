/// <reference lib="webworker" />
/**
 * Loads a board off the main thread: fetch (same-origin, session cookie), JSON parse, render-model
 * build. Large boards (tens of MB of JSON) would otherwise freeze the page for seconds. The parsed
 * design stays here so net highlights can be computed on demand without sending it back.
 */

import type { PCBDesign } from "@via/types";

import type { FromWorker, ToWorker } from "./board-protocol";
import { netGeometry } from "./overlay";
import { buildRenderModel } from "./render-model";

let design: PCBDesign | null = null;
const post = (m: FromWorker) => (self as unknown as Worker).postMessage(m);

self.onmessage = async (e: MessageEvent<ToWorker>) => {
  const msg = e.data;
  if (msg.type === "nets") {
    post({ type: "nets", id: msg.id, geometry: design ? netGeometry(design, msg.names) : { segments: [], circles: [] } });
    return;
  }
  const started = performance.now();
  try {
    const resp = await fetch(msg.url, { credentials: "same-origin", headers: { Accept: "application/json" } });
    if (!resp.ok) {
      let code = "http_error";
      let message = `The board couldn't be loaded (HTTP ${resp.status}).`;
      try {
        const body = (await resp.json()) as { error?: { code?: string; message?: string } };
        code = body.error?.code ?? code;
        message = body.error?.message ?? message;
      } catch {
        // not JSON: keep the generic message
      }
      post({ type: "error", status: resp.status, code, message });
      return;
    }
    design = (await resp.json()) as PCBDesign;
    const model = buildRenderModel(design);
    post({ type: "loaded", model, stats: design.stats, durationMs: performance.now() - started });
  } catch {
    post({ type: "error", status: 0, code: "network_error", message: "The board couldn't be loaded. Check your connection and try again." });
  }
};
