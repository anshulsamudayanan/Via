/**
 * Render model: the viewer's own, draw-ready representation of a parsed board.
 *
 * It is derived from VIA's normalized `PCBDesign` (the API contract) and owns
 * every rendering concern: resolved pad outlines, sampled arcs, per-layer and
 * per-width grouping, draw order, default visibility and component bounding
 * boxes for selection. Renderers (Canvas today, possibly WebGL later) consume
 * only this model, so the data model never has to change for rendering.
 *
 * Arrays of coordinates are flat: [x0, y0, x1, y1, ...] (millimetres).
 */

import type { Footprint, Graphic, LayerKind, PCBDesign, Side } from "@via/types";

import { arcPolyline, type Bounds, emptyBounds, extend, extendFlat, isEmpty, rectPolygon, stadiumPolygon } from "./geometry";

export interface StrokeGroup {
  width: number;
  /** Independent segments: x1, y1, x2, y2 per segment. */
  segments: number[];
  /** Open polylines (arcs, multi-point graphics). */
  polylines: number[][];
}

export interface Circle {
  x: number;
  y: number;
  r: number;
  /** Stroke width; 0 means filled. */
  width: number;
}

export interface LayerPrims {
  name: string;
  kind: LayerKind;
  side: Side;
  /** Draw order: lower first. */
  order: number;
  /** Index among inner copper layers (for colouring). */
  innerIndex: number;
  visibleByDefault: boolean;
  tracks: StrokeGroup[];
  padPolygons: number[][];
  padCircles: Circle[];
  zones: number[][];
  strokes: StrokeGroup[];
  fills: number[][];
  circles: Circle[];
}

export interface RenderComponent {
  index: number;
  reference: string;
  value: string | null;
  footprint: string;
  side: Side;
  x: number;
  y: number;
  rotation: number;
  bbox: Bounds;
  /** Pad outlines for highlighting the selected component. */
  padPolygons: number[][];
  padCircles: Circle[];
  source: Footprint;
}

export interface RenderModel {
  bounds: Bounds;
  layers: LayerPrims[];
  vias: Circle[];
  /** Plated and non-plated holes (drawn last, in the background colour). */
  holes: { polygons: number[][]; circles: Circle[] };
  components: RenderComponent[];
  counts: { tracks: number; pads: number; vias: number; zones: number; components: number };
}

// ------------------------------------------------------------------ layer order

const DEFAULT_VISIBLE: Partial<Record<LayerKind, boolean>> = { copper: true, silkscreen: true, edge: true };

function layerOrder(kind: LayerKind, side: Side, innerIndex: number): number {
  if (side === "bottom") return kind === "copper" ? 20 : kind === "silkscreen" ? 12 : 5;
  if (side === "inner") return 30 + (16 - innerIndex) * 0.1;
  if (side === "top") {
    if (kind === "copper") return 50;
    if (kind === "solder_mask" || kind === "solder_paste" || kind === "adhesive") return 55;
    if (kind === "silkscreen") return 60;
    return 62;
  }
  if (kind === "edge") return 80;
  return 70;
}

// ------------------------------------------------------------------ builders

function addStroke(groups: Map<number, StrokeGroup>, width: number, seg?: number[], poly?: number[]): void {
  const key = Math.round(width * 1000) / 1000;
  let g = groups.get(key);
  if (!g) {
    g = { width: key, segments: [], polylines: [] };
    groups.set(key, g);
  }
  if (seg) g.segments.push(...seg);
  if (poly) g.polylines.push(poly);
}

interface LayerBuild {
  prims: LayerPrims;
  tracks: Map<number, StrokeGroup>;
  strokes: Map<number, StrokeGroup>;
}

function padOutline(
  shape: string,
  x: number,
  y: number,
  w: number,
  h: number,
  rotation: number,
): { polygon?: number[]; circle?: Circle } {
  if (shape === "circle") return { circle: { x, y, r: w / 2, width: 0 } };
  if (shape === "oval") return { polygon: stadiumPolygon(x, y, w, h, rotation) };
  // rect, roundrect, trapezoid, chamfered_rect, custom: drawn as their (rotated) bounding rectangle.
  return { polygon: rectPolygon(x, y, w, h, rotation) };
}

function addGraphic(build: LayerBuild, g: Graphic): void {
  const pts = g.points;
  const p = build.prims;
  switch (g.kind) {
    case "line":
      if (pts.length >= 2) addStroke(build.strokes, g.width, [pts[0]!.x, pts[0]!.y, pts[1]!.x, pts[1]!.y]);
      break;
    case "arc":
      if (pts.length >= 3) {
        addStroke(build.strokes, g.width, undefined, arcPolyline([pts[0]!.x, pts[0]!.y], [pts[1]!.x, pts[1]!.y], [pts[2]!.x, pts[2]!.y]));
      }
      break;
    case "circle":
      if (pts.length >= 2) {
        const r = Math.hypot(pts[1]!.x - pts[0]!.x, pts[1]!.y - pts[0]!.y);
        p.circles.push({ x: pts[0]!.x, y: pts[0]!.y, r, width: g.filled ? 0 : Math.max(g.width, 0) });
      }
      break;
    case "rect":
      if (pts.length >= 2) {
        const [a, b] = [pts[0]!, pts[1]!];
        const poly = [a.x, a.y, b.x, a.y, b.x, b.y, a.x, b.y];
        if (g.filled) p.fills.push(poly);
        else addStroke(build.strokes, g.width, undefined, [...poly, a.x, a.y]);
      }
      break;
    case "polygon": {
      const flat = pts.flatMap((q) => [q.x, q.y]);
      if (g.filled) p.fills.push(flat);
      else if (flat.length >= 4) addStroke(build.strokes, g.width, undefined, [...flat, flat[0]!, flat[1]!]);
      break;
    }
  }
}

function graphicBounds(b: Bounds, g: Graphic): void {
  if (g.kind === "circle" && g.points.length >= 2) {
    const c = g.points[0]!;
    const r = Math.hypot(g.points[1]!.x - c.x, g.points[1]!.y - c.y);
    extend(b, c.x, c.y, r);
    return;
  }
  for (const q of g.points) extend(b, q.x, q.y);
}

const BBOX_LAYER_KINDS = new Set<LayerKind>(["courtyard", "fabrication", "silkscreen"]);

export function buildRenderModel(design: PCBDesign): RenderModel {
  const layerDefs = new Map(design.layers.map((l) => [l.name, l]));
  let innerCounter = 0;
  const innerIndex = new Map<string, number>();
  for (const l of design.layers) if (l.kind === "copper" && l.side === "inner") innerIndex.set(l.name, innerCounter++);

  const builds = new Map<string, LayerBuild>();
  const layer = (name: string): LayerBuild => {
    let b = builds.get(name);
    if (!b) {
      const def = layerDefs.get(name);
      const kind: LayerKind = def?.kind ?? (name.endsWith(".Cu") ? "copper" : "user");
      const side: Side = def?.side ?? (name.startsWith("F.") ? "top" : name.startsWith("B.") ? "bottom" : "none");
      const ii = innerIndex.get(name) ?? 0;
      b = {
        prims: {
          name, kind, side, order: layerOrder(kind, side, ii), innerIndex: ii,
          visibleByDefault: DEFAULT_VISIBLE[kind] ?? false,
          tracks: [], padPolygons: [], padCircles: [], zones: [], strokes: [], fills: [], circles: [],
        },
        tracks: new Map(),
        strokes: new Map(),
      };
      builds.set(name, b);
    }
    return b;
  };

  // Tracks
  for (const t of design.tracks) {
    const b = layer(t.layer);
    if (t.kind === "arc" && t.mid) {
      addStroke(b.tracks, t.width, undefined, arcPolyline([t.start.x, t.start.y], [t.mid.x, t.mid.y], [t.end.x, t.end.y]));
    } else {
      addStroke(b.tracks, t.width, [t.start.x, t.start.y, t.end.x, t.end.y]);
    }
  }

  // Zones (outline polygon on each of their layers; keep-outs are not copper)
  let zoneCount = 0;
  for (const z of design.zones) {
    if (z.keepout || z.outline.length < 3) continue;
    const flat = z.outline.flatMap((q) => [q.x, q.y]);
    for (const name of z.layers) layer(name).prims.zones.push(flat);
    zoneCount++;
  }

  // Board graphics and the outline
  for (const g of design.graphics) addGraphic(layer(g.layer), g);
  for (const g of design.outline.graphics) addGraphic(layer(g.layer), g);

  // Components: pads, footprint graphics, bounding boxes
  const holes = { polygons: [] as number[][], circles: [] as Circle[] };
  const components: RenderComponent[] = [];
  let padCount = 0;
  design.components.forEach((c, index) => {
    const bbox = emptyBounds();
    const fallback = emptyBounds();
    const padPolygons: number[][] = [];
    const padCircles: Circle[] = [];
    for (const pad of c.pads) {
      padCount++;
      const { polygon, circle } = padOutline(pad.shape, pad.position.x, pad.position.y, pad.size.x, pad.size.y, pad.rotation);
      if (polygon) {
        padPolygons.push(polygon);
        extendFlat(bbox, polygon);
      }
      if (circle) {
        padCircles.push(circle);
        extend(bbox, circle.x, circle.y, circle.r);
      }
      for (const name of pad.layers) {
        const def = layerDefs.get(name);
        if ((def?.kind ?? (name.endsWith(".Cu") ? "copper" : "")) !== "copper") continue;
        const prims = layer(name).prims;
        if (polygon) prims.padPolygons.push(polygon);
        if (circle) prims.padCircles.push(circle);
      }
      if (pad.drill && pad.drill.diameter > 0) {
        const ox = pad.position.x + (pad.drill.offset?.x ?? 0);
        const oy = pad.position.y + (pad.drill.offset?.y ?? 0);
        if (pad.drill.slot_length) holes.polygons.push(stadiumPolygon(ox, oy, pad.drill.diameter, pad.drill.slot_length, pad.rotation));
        else holes.circles.push({ x: ox, y: oy, r: pad.drill.diameter / 2, width: 0 });
      }
    }
    for (const g of c.graphics) {
      if (g.layer === "Edge.Cuts") continue; // already part of design.outline
      addGraphic(layer(g.layer), g);
      const kind = layerDefs.get(g.layer)?.kind;
      if (kind && BBOX_LAYER_KINDS.has(kind)) graphicBounds(kind === "courtyard" ? bbox : fallback, g);
    }
    if (isEmpty(bbox)) Object.assign(bbox, fallback);
    if (isEmpty(bbox)) extend(bbox, c.position.x, c.position.y, 0.5);
    components.push({
      index, reference: c.reference, value: c.value, footprint: c.footprint, side: c.side,
      x: c.position.x, y: c.position.y, rotation: c.rotation, bbox, padPolygons, padCircles, source: c,
    });
  });

  const vias: Circle[] = design.vias.map((v) => ({ x: v.position.x, y: v.position.y, r: v.diameter / 2, width: v.drill / 2 }));

  // Bounds: the outline if there is one, otherwise everything drawn.
  const bounds = emptyBounds();
  const bb = design.outline.bbox ?? design.bbox;
  if (bb) {
    extend(bounds, bb.min_x, bb.min_y);
    extend(bounds, bb.max_x, bb.max_y);
  } else {
    for (const c of components) {
      extend(bounds, c.bbox.minX, c.bbox.minY);
      extend(bounds, c.bbox.maxX, c.bbox.maxY);
    }
    for (const t of design.tracks) {
      extend(bounds, t.start.x, t.start.y, t.width);
      extend(bounds, t.end.x, t.end.y, t.width);
    }
  }
  if (isEmpty(bounds)) extend(bounds, 0, 0, 10);

  const layers = [...builds.values()]
    .map(({ prims, tracks, strokes }) => ({ ...prims, tracks: [...tracks.values()], strokes: [...strokes.values()] }))
    .sort((a, b) => a.order - b.order || a.name.localeCompare(b.name));

  return {
    bounds,
    layers,
    vias,
    holes,
    components,
    counts: { tracks: design.tracks.length, pads: padCount, vias: vias.length, zones: zoneCount, components: components.length },
  };
}

// ------------------------------------------------------------------ selection

/**
 * The component under a board-space point: the smallest bounding box that
 * contains it, among components on visible sides. `tolerance` (mm) helps
 * with tiny parts at low zoom.
 */
export function componentAt(
  model: RenderModel,
  x: number,
  y: number,
  visibleSides: ReadonlySet<Side>,
  tolerance = 0,
): RenderComponent | null {
  let best: RenderComponent | null = null;
  let bestArea = Infinity;
  for (const c of model.components) {
    if (!visibleSides.has(c.side)) continue;
    const b = c.bbox;
    if (x < b.minX - tolerance || x > b.maxX + tolerance || y < b.minY - tolerance || y > b.maxY + tolerance) continue;
    const area = (b.maxX - b.minX) * (b.maxY - b.minY);
    if (area < bestArea) {
      best = c;
      bestArea = area;
    }
  }
  return best;
}
