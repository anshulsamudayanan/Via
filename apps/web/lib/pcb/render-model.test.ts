import type { PCBDesign } from "@via/types";
import { describe, expect, it } from "vitest";

import board from "@/test/fixtures/reference-board.json";

import { arcPolyline, circleThrough, rotate } from "./geometry";
import { buildRenderModel, componentAt } from "./render-model";
import { fitViewport, focusOn, panBy, screenToWorld, worldToScreen, zoomAt } from "./viewport";

const design = board as unknown as PCBDesign;
const model = buildRenderModel(design);
const layer = (name: string) => model.layers.find((l) => l.name === name)!;
const close = (a: number, b: number, eps = 1e-6) => Math.abs(a - b) < eps;

describe("geometry (engine conventions)", () => {
  it("rotates CCW on a Y-down screen", () => {
    const [x, y] = rotate([1, 0], 90);
    expect(close(x, 0) && close(y, -1)).toBe(true);
  });
  it("samples arcs through their mid point", () => {
    const pts = arcPolyline([120, 112], [121, 113], [120, 114]);
    expect(pts.slice(0, 2)).toEqual([120, 112]);
    expect(pts.slice(-2)).toEqual([120, 114]);
    const xs = pts.filter((_, i) => i % 2 === 0);
    expect(Math.max(...xs)).toBeCloseTo(121, 2); // bulges to x = 121 (8° chords: < 0.003 mm sagitta)
    expect(circleThrough([0, 0], [1, 1], [2, 2])).toBeNull();
  });
});

describe("buildRenderModel (reference board)", () => {
  it("uses the board outline as bounds", () => {
    expect(model.bounds).toEqual({ minX: 100, minY: 100, maxX: 150, maxY: 130 });
  });

  it("orders layers back-to-front and sets default visibility", () => {
    const names = model.layers.map((l) => l.name);
    expect(names.indexOf("B.Cu")).toBeLessThan(names.indexOf("F.Cu"));
    expect(names.indexOf("F.Cu")).toBeLessThan(names.indexOf("F.SilkS"));
    expect(names[names.length - 1]).toBe("Edge.Cuts");
    expect(layer("F.Cu").visibleByDefault).toBe(true);
    expect(layer("Edge.Cuts").visibleByDefault).toBe(true);
    expect(layer("F.CrtYd").visibleByDefault).toBe(false);
  });

  it("groups tracks by layer and width", () => {
    const fcu = layer("F.Cu").tracks;
    expect(fcu.map((g) => [g.width, g.segments.length / 4]).sort()).toEqual([[0.25, 3], [0.3, 1]]);
    const bcu = layer("B.Cu").tracks;
    const w03 = bcu.find((g) => g.width === 0.3)!;
    expect(w03.segments.length / 4).toBe(2);
    expect(w03.polylines).toHaveLength(1); // the arc track
    expect(model.counts).toMatchObject({ tracks: 8, pads: 7, vias: 1, zones: 1, components: 4 });
  });

  it("resolves pad outlines, rotation and copper layers", () => {
    const r1 = model.components.find((c) => c.reference === "R1")!;
    const pad1 = r1.padPolygons[0]!; // 0.8 x 0.95 at (109.175, 110)
    const xs = pad1.filter((_, i) => i % 2 === 0);
    const ys = pad1.filter((_, i) => i % 2 === 1);
    expect(Math.max(...xs) - Math.min(...xs)).toBeCloseTo(0.8);
    expect(Math.max(...ys) - Math.min(...ys)).toBeCloseTo(0.95);
    const c1 = model.components.find((c) => c.reference === "C1")!; // rotated 90°: 0.9 x 0.95 swaps axes
    const c1xs = c1.padPolygons[0]!.filter((_, i) => i % 2 === 0);
    expect(Math.max(...c1xs) - Math.min(...c1xs)).toBeCloseTo(0.95);
    // Through-hole pads (J1) and the NPTH hole appear on both copper layers.
    expect(layer("F.Cu").padPolygons.length + layer("F.Cu").padCircles.length).toBe(2 + 2 + 1);
    expect(layer("B.Cu").padPolygons.length + layer("B.Cu").padCircles.length).toBe(2 + 2 + 1);
    expect(model.holes.circles.map((h) => h.r).sort()).toEqual([0.5, 0.5, 1.6]);
  });

  it("includes vias, zones and graphics", () => {
    expect(model.vias).toEqual([{ x: 118, y: 110, r: 0.3, width: 0.15 }]);
    expect(layer("B.Cu").zones).toHaveLength(1);
    expect(layer("Edge.Cuts").strokes[0]!.segments.length / 4).toBe(4);
    expect(layer("F.SilkS").circles).toHaveLength(1); // board-level silk circle
    expect(layer("F.Fab").circles).toHaveLength(1); // J1's fab circle
  });

  it("computes component bounding boxes from courtyards", () => {
    const r1 = model.components.find((c) => c.reference === "R1")!;
    expect(r1.bbox.minX).toBeCloseTo(110 - 1.48);
    expect(r1.bbox.maxY).toBeCloseTo(110 + 0.73);
  });
});

describe("componentAt", () => {
  const both = new Set(["top", "bottom"] as const);
  it("finds the component under a point", () => {
    expect(componentAt(model, 109.2, 110, both)?.reference).toBe("R1");
    expect(componentAt(model, 140, 117.5, both)?.reference).toBe("J1");
    expect(componentAt(model, 130, 125, both)).toBeNull();
  });
  it("ignores components on hidden sides", () => {
    expect(componentAt(model, 120, 115, both)?.reference).toBe("C1");
    expect(componentAt(model, 120, 115, new Set(["top"] as const))).toBeNull();
  });
});

describe("viewport", () => {
  it("fits the board centred with a margin", () => {
    const vp = fitViewport(model.bounds, 1000, 600);
    const [x0, y0] = worldToScreen(vp, 100, 100);
    const [x1, y1] = worldToScreen(vp, 150, 130);
    expect(x0).toBeGreaterThan(0);
    expect(x1).toBeLessThan(1000);
    expect((x0 + x1) / 2).toBeCloseTo(500);
    expect((y0 + y1) / 2).toBeCloseTo(300);
    expect(Math.min(x0, 1000 - x1, y0, 600 - y1)).toBeGreaterThanOrEqual(35);
  });
  it("zooms around the cursor and pans", () => {
    const vp = fitViewport(model.bounds, 1000, 600);
    const before = screenToWorld(vp, 250, 150);
    const zoomed = zoomAt(vp, 2, 250, 150, vp.scale / 5);
    expect(zoomed.scale).toBeCloseTo(vp.scale * 2);
    const after = screenToWorld(zoomed, 250, 150);
    expect(after[0]).toBeCloseTo(before[0]);
    expect(after[1]).toBeCloseTo(before[1]);
    expect(zoomAt(vp, 0.0001, 0, 0, vp.scale / 5).scale).toBeCloseTo(vp.scale / 5);
    expect(panBy(vp, 10, -5)).toEqual({ ...vp, tx: vp.tx + 10, ty: vp.ty - 5 });
  });
  it("focuses on a component", () => {
    const r1 = model.components.find((c) => c.reference === "R1")!;
    const vp = focusOn(r1.bbox, 1000, 600);
    const [cx, cy] = worldToScreen(vp, (r1.bbox.minX + r1.bbox.maxX) / 2, (r1.bbox.minY + r1.bbox.maxY) / 2);
    expect(cx).toBeCloseTo(500);
    expect(cy).toBeCloseTo(300);
  });
});
