/** Messages between the board loader and its Web Worker. */

import type { DesignStats } from "@via/types";

import type { NetGeometry } from "./overlay";
import type { RenderModel } from "./render-model";

export type ToWorker = { type: "load"; url: string } | { type: "nets"; id: number; names: string[] };

export type FromWorker =
  | { type: "loaded"; model: RenderModel; stats: DesignStats; durationMs: number }
  | { type: "error"; status: number; code: string; message: string }
  | { type: "nets"; id: number; geometry: NetGeometry };
