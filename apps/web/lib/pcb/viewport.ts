/**
 * Viewport math for the board viewer. Screen = world * scale + translate,
 * where world is board millimetres and screen is CSS pixels.
 */

import type { Bounds } from "./geometry";

export interface Viewport {
  /** CSS pixels per millimetre. */
  scale: number;
  tx: number;
  ty: number;
}

export const MAX_SCALE = 4000;

/** Fit `bounds` into a w x h canvas with a margin (fraction of the smaller side). */
export function fitViewport(bounds: Bounds, width: number, height: number, margin = 0.06): Viewport {
  const bw = Math.max(bounds.maxX - bounds.minX, 1e-3);
  const bh = Math.max(bounds.maxY - bounds.minY, 1e-3);
  const usableW = Math.max(width * (1 - 2 * margin), 1);
  const usableH = Math.max(height * (1 - 2 * margin), 1);
  const scale = Math.min(usableW / bw, usableH / bh);
  const cx = (bounds.minX + bounds.maxX) / 2;
  const cy = (bounds.minY + bounds.maxY) / 2;
  return { scale, tx: width / 2 - cx * scale, ty: height / 2 - cy * scale };
}

export function screenToWorld(vp: Viewport, sx: number, sy: number): [number, number] {
  return [(sx - vp.tx) / vp.scale, (sy - vp.ty) / vp.scale];
}

export function worldToScreen(vp: Viewport, x: number, y: number): [number, number] {
  return [x * vp.scale + vp.tx, y * vp.scale + vp.ty];
}

/** Zoom by `factor` keeping the screen point (sx, sy) fixed. */
export function zoomAt(vp: Viewport, factor: number, sx: number, sy: number, minScale: number, maxScale = MAX_SCALE): Viewport {
  const scale = Math.min(Math.max(vp.scale * factor, minScale), maxScale);
  const [wx, wy] = screenToWorld(vp, sx, sy);
  return { scale, tx: sx - wx * scale, ty: sy - wy * scale };
}

export function panBy(vp: Viewport, dx: number, dy: number): Viewport {
  return { ...vp, tx: vp.tx + dx, ty: vp.ty + dy };
}

/** Centre on a region (e.g. a selected component), zooming so it fills ~`fill` of the view. */
export function focusOn(bounds: Bounds, width: number, height: number, fill = 0.35, maxScale = MAX_SCALE): Viewport {
  const vp = fitViewport(bounds, width * fill, height * fill, 0);
  const scale = Math.min(vp.scale, maxScale);
  const cx = (bounds.minX + bounds.maxX) / 2;
  const cy = (bounds.minY + bounds.maxY) / 2;
  return { scale, tx: width / 2 - cx * scale, ty: height / 2 - cy * scale };
}
