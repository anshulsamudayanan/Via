/**
 * Overlays drawn on top of the board: finding regions, highlighted components and nets.
 * Geometry comes from the parsed design; nothing here is inferred.
 */

import type { BoundingBox, PCBDesign, Severity } from "@via/types";

import type { Bounds } from "./geometry";
import type { Circle, RenderComponent, RenderModel } from "./render-model";

export interface Highlight {
  /** Component references to outline. */
  references: string[];
  /** Net names whose copper (tracks, vias, pads) is drawn highlighted. */
  nets: string[];
  /** Finding regions, coloured by severity. */
  regions: { bbox: BoundingBox; severity: Severity; points?: { x: number; y: number }[] }[];
  /** Zoom to the highlight when it changes. */
  focus?: boolean;
}

export const EMPTY_HIGHLIGHT: Highlight = { references: [], nets: [], regions: [] };

/** Copper of a set of nets: segments as flat [x1, y1, x2, y2, width] quintuples, plus pad/via discs. */
export interface NetGeometry {
  segments: number[];
  circles: Circle[];
}

export function netGeometry(design: PCBDesign, names: readonly string[]): NetGeometry {
  const wanted = new Set(names);
  const segments: number[] = [];
  const circles: Circle[] = [];
  if (!wanted.size) return { segments, circles };
  for (const t of design.tracks) {
    if (!t.net || !wanted.has(t.net)) continue;
    if (t.kind === "arc" && t.mid) {
      // Two chords through the arc midpoint: close enough to show where the net runs.
      segments.push(t.start.x, t.start.y, t.mid.x, t.mid.y, t.width, t.mid.x, t.mid.y, t.end.x, t.end.y, t.width);
    } else {
      segments.push(t.start.x, t.start.y, t.end.x, t.end.y, t.width);
    }
  }
  for (const v of design.vias) if (v.net && wanted.has(v.net)) circles.push({ x: v.position.x, y: v.position.y, r: v.diameter / 2, width: 0 });
  for (const c of design.components) {
    for (const p of c.pads) {
      if (p.net && wanted.has(p.net)) circles.push({ x: p.position.x, y: p.position.y, r: Math.max(p.size.x, p.size.y) / 2, width: 0 });
    }
  }
  return { segments, circles };
}

export interface ResolvedOverlay {
  components: RenderComponent[];
  net: NetGeometry | null;
  regions: Highlight["regions"];
}

export function resolveComponents(model: RenderModel, references: readonly string[]): RenderComponent[] {
  if (!references.length) return [];
  const wanted = new Set(references);
  return model.components.filter((c) => wanted.has(c.reference));
}

/** Bounds enclosing everything highlighted (regions, components, net copper), or null. */
export function overlayBounds(o: ResolvedOverlay): Bounds | null {
  let minX = Infinity;
  let minY = Infinity;
  let maxX = -Infinity;
  let maxY = -Infinity;
  const add = (x: number, y: number) => {
    minX = Math.min(minX, x);
    minY = Math.min(minY, y);
    maxX = Math.max(maxX, x);
    maxY = Math.max(maxY, y);
  };
  for (const r of o.regions) {
    add(r.bbox.min_x, r.bbox.min_y);
    add(r.bbox.max_x, r.bbox.max_y);
  }
  for (const c of o.components) {
    add(c.bbox.minX, c.bbox.minY);
    add(c.bbox.maxX, c.bbox.maxY);
  }
  if (o.net) {
    const s = o.net.segments;
    for (let i = 0; i < s.length; i += 5) {
      add(s[i]!, s[i + 1]!);
      add(s[i + 2]!, s[i + 3]!);
    }
    for (const c of o.net.circles) add(c.x, c.y);
  }
  return Number.isFinite(minX) ? { minX, minY, maxX, maxY } : null;
}
