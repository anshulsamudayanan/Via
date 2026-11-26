/**
 * Load a parsed board for the viewer: in a Web Worker when the browser has one (so parsing a large
 * board never blocks the page), on the main thread otherwise (tests, very old browsers).
 */

import { ApiError, type ViaClient } from "@via/api-client";
import type { DesignStats } from "@via/types";

import type { FromWorker, ToWorker } from "./board-protocol";
import { type NetGeometry, netGeometry } from "./overlay";
import { buildRenderModel, type RenderModel } from "./render-model";

export interface LoadedBoard {
  model: RenderModel;
  stats: DesignStats;
  /** Copper of the named nets, for highlighting. */
  nets(names: string[]): Promise<NetGeometry>;
  dispose(): void;
}

function normalizedUrl(designId: string, revisionId?: string): string {
  const q = revisionId ? `?revision_id=${encodeURIComponent(revisionId)}` : "";
  return `/api/v1/pcb/${encodeURIComponent(designId)}/normalized${q}`;
}

export function loadBoard(client: ViaClient, designId: string, revisionId: string | undefined, signal: AbortSignal): Promise<LoadedBoard> {
  if (typeof Worker === "undefined") return loadInline(client, designId, revisionId, signal);
  let worker: Worker;
  try {
    worker = new Worker(new URL("./board.worker.ts", import.meta.url), { type: "module" });
  } catch {
    return loadInline(client, designId, revisionId, signal);
  }
  return new Promise<LoadedBoard>((resolve, reject) => {
    let nextId = 1;
    const pending = new Map<number, (g: NetGeometry) => void>();
    const dispose = () => {
      worker.terminate();
      for (const done of pending.values()) done({ segments: [], circles: [] });
      pending.clear();
    };
    signal.addEventListener("abort", () => {
      dispose();
      reject(new DOMException("Aborted", "AbortError"));
    }, { once: true });
    worker.onerror = () => {
      dispose();
      // A worker that fails to start (e.g. blocked by policy) falls back to the main thread.
      loadInline(client, designId, revisionId, signal).then(resolve, reject);
    };
    worker.onmessage = (e: MessageEvent<FromWorker>) => {
      const m = e.data;
      if (m.type === "error") {
        dispose();
        reject(new ApiError(m.status, m.code, m.message));
      } else if (m.type === "loaded") {
        resolve({
          model: m.model,
          stats: m.stats,
          nets: (names) =>
            new Promise((done) => {
              const id = nextId++;
              pending.set(id, done);
              worker.postMessage({ type: "nets", id, names } satisfies ToWorker);
            }),
          dispose,
        });
      } else if (m.type === "nets") {
        pending.get(m.id)?.(m.geometry);
        pending.delete(m.id);
      }
    };
    worker.postMessage({ type: "load", url: normalizedUrl(designId, revisionId) } satisfies ToWorker);
  });
}

async function loadInline(client: ViaClient, designId: string, revisionId: string | undefined, signal: AbortSignal): Promise<LoadedBoard> {
  const design = await client.pcb.normalized(designId, revisionId, signal);
  return {
    model: buildRenderModel(design),
    stats: design.stats,
    nets: async (names) => netGeometry(design, names),
    dispose: () => undefined,
  };
}
