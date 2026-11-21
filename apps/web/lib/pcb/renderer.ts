/**
 * Canvas 2D renderer for the board viewer.
 *
 * Geometry is traced once into cached Path2D objects (per layer, per stroke
 * width), so panning and zooming only re-play a handful of paths per frame,
 * even for boards with hundreds of thousands of tracks. Everything is drawn in
 * board millimetres under a single transform; hairlines get a 1 px minimum.
 */

import type { Side } from "@via/types";

import { layerColor, type Theme, VIEWER_COLORS } from "./palette";
import type { Circle, LayerPrims, RenderComponent, RenderModel, StrokeGroup } from "./render-model";
import type { Viewport } from "./viewport";

export interface ObjectToggles {
  tracks: boolean;
  pads: boolean;
  vias: boolean;
  zones: boolean;
}

export interface DrawOptions {
  viewport: Viewport;
  width: number;
  height: number;
  dpr: number;
  theme: Theme;
  visibleLayers: ReadonlySet<string>;
  show: ObjectToggles;
  selected: RenderComponent | null;
}

interface PathSink {
  moveTo(x: number, y: number): void;
  lineTo(x: number, y: number): void;
  arc(x: number, y: number, r: number, a0: number, a1: number): void;
  closePath(): void;
}

function traceSegments(sink: PathSink, flat: readonly number[]): void {
  for (let i = 0; i < flat.length; i += 4) {
    sink.moveTo(flat[i]!, flat[i + 1]!);
    sink.lineTo(flat[i + 2]!, flat[i + 3]!);
  }
}

function tracePolyline(sink: PathSink, flat: readonly number[], close: boolean): void {
  if (flat.length < 4) return;
  sink.moveTo(flat[0]!, flat[1]!);
  for (let i = 2; i < flat.length; i += 2) sink.lineTo(flat[i]!, flat[i + 1]!);
  if (close) sink.closePath();
}

function traceCircle(sink: PathSink, c: Circle): void {
  sink.moveTo(c.x + c.r, c.y);
  sink.arc(c.x, c.y, c.r, 0, Math.PI * 2);
}

// ------------------------------------------------------------------ path cache

interface LayerPaths {
  tracks: { width: number; path: Path2D }[];
  pads: Path2D;
  zones: Path2D;
  strokes: { width: number; path: Path2D }[];
  fills: Path2D;
  filledCircles: Path2D;
  strokedCircles: { width: number; path: Path2D }[];
}

interface ModelPaths {
  layers: Map<string, LayerPaths>;
  vias: Path2D;
  viaHoles: Path2D;
  holes: Path2D;
}

const cache = new WeakMap<RenderModel, ModelPaths>();

function strokePaths(groups: StrokeGroup[]): { width: number; path: Path2D }[] {
  return groups.map((g) => {
    const path = new Path2D();
    traceSegments(path, g.segments);
    for (const poly of g.polylines) tracePolyline(path, poly, false);
    return { width: g.width, path };
  });
}

function buildLayerPaths(l: LayerPrims): LayerPaths {
  const pads = new Path2D();
  for (const poly of l.padPolygons) tracePolyline(pads, poly, true);
  for (const c of l.padCircles) traceCircle(pads, c);
  const zones = new Path2D();
  for (const z of l.zones) tracePolyline(zones, z, true);
  const fills = new Path2D();
  for (const f of l.fills) tracePolyline(fills, f, true);
  const filledCircles = new Path2D();
  const byWidth = new Map<number, Path2D>();
  for (const c of l.circles) {
    if (c.width === 0) traceCircle(filledCircles, c);
    else {
      let p = byWidth.get(c.width);
      if (!p) byWidth.set(c.width, (p = new Path2D()));
      traceCircle(p, c);
    }
  }
  return {
    tracks: strokePaths(l.tracks),
    pads,
    zones,
    strokes: strokePaths(l.strokes),
    fills,
    filledCircles,
    strokedCircles: [...byWidth.entries()].map(([width, path]) => ({ width, path })),
  };
}

function pathsFor(model: RenderModel): ModelPaths {
  let paths = cache.get(model);
  if (!paths) {
    const vias = new Path2D();
    const viaHoles = new Path2D();
    for (const v of model.vias) {
      traceCircle(vias, v);
      traceCircle(viaHoles, { x: v.x, y: v.y, r: v.width, width: 0 });
    }
    const holes = new Path2D();
    for (const h of model.holes.circles) traceCircle(holes, h);
    for (const p of model.holes.polygons) tracePolyline(holes, p, true);
    paths = { layers: new Map(model.layers.map((l) => [l.name, buildLayerPaths(l)])), vias, viaHoles, holes };
    cache.set(model, paths);
  }
  return paths;
}

// ------------------------------------------------------------------ drawing

/** Sides that count as visible for selection: any visible layer on that side. */
export function visibleSides(model: RenderModel, visibleLayers: ReadonlySet<string>): Set<Side> {
  const sides = new Set<Side>();
  for (const l of model.layers) if (visibleLayers.has(l.name) && (l.side === "top" || l.side === "bottom")) sides.add(l.side);
  return sides;
}

export function drawBoard(ctx: CanvasRenderingContext2D, model: RenderModel, opts: DrawOptions): void {
  const { viewport: vp, dpr, theme } = opts;
  const colors = VIEWER_COLORS[theme];
  const paths = pathsFor(model);
  const px = 1 / vp.scale; // one CSS pixel in millimetres

  ctx.setTransform(dpr, 0, 0, dpr, 0, 0);
  ctx.fillStyle = colors.background;
  ctx.fillRect(0, 0, opts.width, opts.height);
  ctx.setTransform(dpr * vp.scale, 0, 0, dpr * vp.scale, dpr * vp.tx, dpr * vp.ty);
  ctx.lineCap = "round";
  ctx.lineJoin = "round";

  let anyCopperVisible = false;
  for (const layer of model.layers) {
    if (!opts.visibleLayers.has(layer.name)) continue;
    const lp = paths.layers.get(layer.name);
    if (!lp) continue;
    const color = layerColor(layer.name, layer.kind, layer.side, layer.innerIndex, theme);
    ctx.strokeStyle = color;
    ctx.fillStyle = color;
    const copper = layer.kind === "copper";
    if (copper) anyCopperVisible = true;

    if (copper && opts.show.zones && layer.zones.length) {
      ctx.globalAlpha = 0.12;
      ctx.fill(lp.zones, "evenodd");
    }
    ctx.globalAlpha = copper ? 0.85 : 0.9;
    if (!copper || opts.show.tracks) {
      for (const t of lp.tracks) {
        ctx.lineWidth = Math.max(t.width, px);
        ctx.stroke(t.path);
      }
    }
    if (copper && opts.show.pads) ctx.fill(lp.pads, "nonzero");
    for (const s of lp.strokes) {
      ctx.lineWidth = Math.max(s.width, px);
      ctx.stroke(s.path);
    }
    ctx.fill(lp.fills, "evenodd");
    ctx.fill(lp.filledCircles);
    for (const c of lp.strokedCircles) {
      ctx.lineWidth = Math.max(c.width, px);
      ctx.stroke(c.path);
    }
  }
  ctx.globalAlpha = 1;

  if (anyCopperVisible && opts.show.vias && model.vias.length) {
    ctx.fillStyle = colors.via;
    ctx.fill(paths.vias);
    ctx.fillStyle = colors.hole;
    ctx.fill(paths.viaHoles);
  }
  if (anyCopperVisible && opts.show.pads) {
    ctx.fillStyle = colors.hole;
    ctx.fill(paths.holes, "nonzero");
  }

  const sel = opts.selected;
  if (sel) {
    const b = sel.bbox;
    const pad = 4 * px;
    ctx.fillStyle = colors.selectionFill;
    ctx.fillRect(b.minX - pad, b.minY - pad, b.maxX - b.minX + 2 * pad, b.maxY - b.minY + 2 * pad);
    ctx.strokeStyle = colors.selection;
    ctx.lineWidth = 1.5 * px;
    ctx.strokeRect(b.minX - pad, b.minY - pad, b.maxX - b.minX + 2 * pad, b.maxY - b.minY + 2 * pad);
    ctx.lineWidth = 1.25 * px;
    ctx.beginPath();
    for (const poly of sel.padPolygons) tracePolyline(ctx, poly, true);
    for (const c of sel.padCircles) traceCircle(ctx, c);
    ctx.stroke();
  }
}
