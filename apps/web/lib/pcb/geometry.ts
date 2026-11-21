/**
 * Geometry helpers matching the PCB engine's conventions (services/pcb-engine
 * geometry): millimetres, +Y down, positive angles counter-clockwise on screen.
 */

export type Vec = readonly [number, number];

export function rotate([x, y]: Vec, deg: number): [number, number] {
  if (!deg) return [x, y];
  const a = (deg * Math.PI) / 180;
  const c = Math.cos(a);
  const s = Math.sin(a);
  return [x * c + y * s, -x * s + y * c];
}

/** Centre and radius of the circle through three points, or null if collinear. */
export function circleThrough(a: Vec, b: Vec, c: Vec): { cx: number; cy: number; r: number } | null {
  const d = 2 * (a[0] * (b[1] - c[1]) + b[0] * (c[1] - a[1]) + c[0] * (a[1] - b[1]));
  if (Math.abs(d) < 1e-12) return null;
  const a2 = a[0] ** 2 + a[1] ** 2;
  const b2 = b[0] ** 2 + b[1] ** 2;
  const c2 = c[0] ** 2 + c[1] ** 2;
  const cx = (a2 * (b[1] - c[1]) + b2 * (c[1] - a[1]) + c2 * (a[1] - b[1])) / d;
  const cy = (a2 * (c[0] - b[0]) + b2 * (a[0] - c[0]) + c2 * (b[0] - a[0])) / d;
  return { cx, cy, r: Math.hypot(a[0] - cx, a[1] - cy) };
}

/** Polyline through an arc defined by start, mid and end points (flat [x0, y0, x1, y1, ...]). */
export function arcPolyline(start: Vec, mid: Vec, end: Vec, maxStepDeg = 8): number[] {
  const circ = circleThrough(start, mid, end);
  if (!circ) return [start[0], start[1], end[0], end[1]];
  const { cx, cy, r } = circ;
  const a0 = Math.atan2(start[1] - cy, start[0] - cx);
  const am = Math.atan2(mid[1] - cy, mid[0] - cx);
  const a1 = Math.atan2(end[1] - cy, end[0] - cx);
  const ccw = (from: number, to: number) => (((to - from) % (2 * Math.PI)) + 2 * Math.PI) % (2 * Math.PI);
  let sweep = ccw(a0, a1);
  if (ccw(a0, am) > sweep) sweep -= 2 * Math.PI;
  const steps = Math.max(2, Math.ceil(Math.abs((sweep * 180) / Math.PI) / maxStepDeg));
  const out: number[] = [];
  for (let i = 0; i <= steps; i++) {
    const t = a0 + (sweep * i) / steps;
    out.push(cx + r * Math.cos(t), cy + r * Math.sin(t));
  }
  out[0] = start[0];
  out[1] = start[1];
  out[out.length - 2] = end[0];
  out[out.length - 1] = end[1];
  return out;
}

/** Rectangle of size w x h centred on (cx, cy), rotated by `deg`, as a closed polygon (flat). */
export function rectPolygon(cx: number, cy: number, w: number, h: number, deg: number): number[] {
  const hw = w / 2;
  const hh = h / 2;
  const out: number[] = [];
  for (const corner of [[-hw, -hh], [hw, -hh], [hw, hh], [-hw, hh]] as const) {
    const [x, y] = rotate(corner, deg);
    out.push(cx + x, cy + y);
  }
  return out;
}

/** Stadium (oval pad / slot): w x h with fully rounded short ends, rotated by `deg`. */
export function stadiumPolygon(cx: number, cy: number, w: number, h: number, deg: number, segments = 8): number[] {
  if (Math.abs(w - h) < 1e-9) {
    const out: number[] = [];
    for (let i = 0; i < segments * 2; i++) {
      const t = (i / (segments * 2)) * 2 * Math.PI;
      out.push(cx + (w / 2) * Math.cos(t), cy + (w / 2) * Math.sin(t));
    }
    return out;
  }
  const horizontal = w > h;
  const r = (horizontal ? h : w) / 2;
  const half = (horizontal ? w : h) / 2 - r;
  const local: [number, number][] = [];
  // Two semicircles joined by straight sides, in local coordinates (long axis = x).
  for (let i = 0; i <= segments; i++) {
    const t = -Math.PI / 2 + (Math.PI * i) / segments;
    local.push([half + r * Math.cos(t), r * Math.sin(t)]);
  }
  for (let i = 0; i <= segments; i++) {
    const t = Math.PI / 2 + (Math.PI * i) / segments;
    local.push([-half + r * Math.cos(t), r * Math.sin(t)]);
  }
  const extra = horizontal ? 0 : 90;
  const out: number[] = [];
  for (const p of local) {
    const [x, y] = rotate(p, deg + extra);
    out.push(cx + x, cy + y);
  }
  return out;
}

export interface Bounds {
  minX: number;
  minY: number;
  maxX: number;
  maxY: number;
}

export function emptyBounds(): Bounds {
  return { minX: Infinity, minY: Infinity, maxX: -Infinity, maxY: -Infinity };
}

export function extend(b: Bounds, x: number, y: number, pad = 0): void {
  if (x - pad < b.minX) b.minX = x - pad;
  if (y - pad < b.minY) b.minY = y - pad;
  if (x + pad > b.maxX) b.maxX = x + pad;
  if (y + pad > b.maxY) b.maxY = y + pad;
}

export function extendFlat(b: Bounds, flat: readonly number[], pad = 0): void {
  for (let i = 0; i < flat.length; i += 2) extend(b, flat[i]!, flat[i + 1]!, pad);
}

export const isEmpty = (b: Bounds) => b.minX > b.maxX;
