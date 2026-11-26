import type { PCBDesign } from "@via/types";
import { describe, expect, it } from "vitest";

import board from "@/test/fixtures/reference-board.json";

import { netGeometry, overlayBounds, resolveComponents } from "./overlay";
import { buildRenderModel } from "./render-model";
import { drawBoard } from "./renderer";
import { fitViewport } from "./viewport";

const design = board as unknown as PCBDesign;
const model = buildRenderModel(design);

describe("net geometry", () => {
  it("collects the net's tracks, vias and pads from the design", () => {
    const net = design.tracks.find((t) => t.net)!.net!;
    const g = netGeometry(design, [net]);
    const tracks = design.tracks.filter((t) => t.net === net);
    const segments = tracks.reduce((n, t) => n + (t.kind === "arc" && t.mid ? 2 : 1), 0);
    expect(g.segments.length).toBe(segments * 5);
    const vias = design.vias.filter((v) => v.net === net).length;
    const pads = design.components.flatMap((c) => c.pads).filter((p) => p.net === net).length;
    expect(g.circles.length).toBe(vias + pads);
    expect(netGeometry(design, []).segments).toEqual([]);
    expect(netGeometry(design, ["no such net"]).circles).toEqual([]);
  });

  it("bounds everything highlighted", () => {
    const comps = resolveComponents(model, ["R1"]);
    expect(comps.map((c) => c.reference)).toEqual(["R1"]);
    const region = { bbox: { min_x: -5, min_y: -6, max_x: -4, max_y: -3 }, severity: "high" as const };
    const b = overlayBounds({ components: comps, net: null, regions: [region] })!;
    expect(b.minX).toBe(-5);
    expect(b.minY).toBe(-6);
    expect(b.maxX).toBe(comps[0]!.bbox.maxX);
    expect(overlayBounds({ components: [], net: null, regions: [] })).toBeNull();
  });
});

describe("overlay drawing", () => {
  it("draws regions in their severity colour and highlights components and nets", () => {
    const calls: { op: string; style: string }[] = [];
    const ctx = {
      strokeStyle: "", fillStyle: "", lineWidth: 1, globalAlpha: 1, lineCap: "", lineJoin: "",
      setTransform: () => {}, setLineDash: () => {}, beginPath: () => {}, moveTo: () => {}, lineTo: () => {}, arc: () => {}, closePath: () => {},
      fillRect: () => calls.push({ op: "fillRect", style: String(ctx.fillStyle) }),
      strokeRect: () => calls.push({ op: "strokeRect", style: String(ctx.strokeStyle) }),
      stroke: () => calls.push({ op: "stroke", style: String(ctx.strokeStyle) }),
      fill: () => calls.push({ op: "fill", style: String(ctx.fillStyle) }),
    };
    const net = design.tracks.find((t) => t.net)!.net!;
    drawBoard(ctx as unknown as CanvasRenderingContext2D, model, {
      viewport: fitViewport(model.bounds, 800, 600), width: 800, height: 600, dpr: 1, theme: "dark",
      visibleLayers: new Set(), show: { tracks: true, pads: true, vias: true, zones: true }, selected: null,
      overlay: {
        components: resolveComponents(model, ["R1"]),
        net: netGeometry(design, [net]),
        regions: [{ bbox: { min_x: 1, min_y: 1, max_x: 2, max_y: 2 }, severity: "critical" }],
      },
    });
    expect(calls).toContainEqual({ op: "strokeRect", style: "#ff4d5e" }); // critical region
    expect(calls).toContainEqual({ op: "strokeRect", style: "#ffd84a" }); // highlighted component
    expect(calls.filter((c) => c.op === "stroke" && c.style === "#ffd84a").length).toBeGreaterThan(0); // net copper
  });
});
