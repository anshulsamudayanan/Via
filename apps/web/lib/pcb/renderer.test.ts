import type { PCBDesign } from "@via/types";
import { describe, expect, it } from "vitest";

import board from "@/test/fixtures/reference-board.json";

import { layerColor } from "./palette";
import { buildRenderModel } from "./render-model";
import { drawBoard, visibleSides } from "./renderer";
import { fitViewport } from "./viewport";

const model = buildRenderModel(board as unknown as PCBDesign);

/** Minimal 2D context that records strokes/fills with the colour in effect. */
function recordingContext() {
  const calls: { op: string; style: string; arg?: unknown }[] = [];
  const ctx = {
    strokeStyle: "",
    fillStyle: "",
    lineWidth: 1,
    globalAlpha: 1,
    lineCap: "butt",
    lineJoin: "miter",
    setTransform: () => {},
    fillRect: (...a: number[]) => calls.push({ op: "fillRect", style: String(ctx.fillStyle), arg: a }),
    strokeRect: (...a: number[]) => calls.push({ op: "strokeRect", style: String(ctx.strokeStyle), arg: a }),
    stroke: (p?: unknown) => calls.push({ op: "stroke", style: String(ctx.strokeStyle), arg: p }),
    fill: (p?: unknown) => calls.push({ op: "fill", style: String(ctx.fillStyle), arg: p }),
    beginPath: () => {},
    moveTo: () => {},
    lineTo: () => {},
    arc: () => {},
    closePath: () => {},
  };
  return { ctx: ctx as unknown as CanvasRenderingContext2D, calls };
}

const base = {
  viewport: fitViewport(model.bounds, 800, 600),
  width: 800,
  height: 600,
  dpr: 1,
  theme: "dark" as const,
  show: { tracks: true, pads: true, vias: true, zones: true },
  selected: null,
};

describe("drawBoard", () => {
  it("draws only visible layers", () => {
    const { ctx, calls } = recordingContext();
    drawBoard(ctx, model, { ...base, visibleLayers: new Set(["B.Cu"]) });
    const fcu = layerColor("F.Cu", "copper", "top", 0, "dark");
    const bcu = layerColor("B.Cu", "copper", "bottom", 0, "dark");
    expect(calls.some((c) => c.style === bcu && c.op === "stroke")).toBe(true);
    expect(calls.some((c) => c.style === fcu)).toBe(false);
  });

  it("respects object toggles", () => {
    const visible = new Set(["F.Cu", "B.Cu"]);
    const withVias = recordingContext();
    drawBoard(withVias.ctx, model, { ...base, visibleLayers: visible });
    const noVias = recordingContext();
    drawBoard(noVias.ctx, model, { ...base, visibleLayers: visible, show: { ...base.show, vias: false, tracks: false } });
    const via = "#c9ced6";
    expect(withVias.calls.some((c) => c.style === via)).toBe(true);
    expect(noVias.calls.some((c) => c.style === via)).toBe(false);
    expect(noVias.calls.filter((c) => c.op === "stroke").length).toBeLessThan(withVias.calls.filter((c) => c.op === "stroke").length);
  });

  it("highlights the selected component", () => {
    const { ctx, calls } = recordingContext();
    const r1 = model.components.find((c) => c.reference === "R1")!;
    drawBoard(ctx, model, { ...base, visibleLayers: new Set(["F.Cu"]), selected: r1 });
    const rect = calls.find((c) => c.op === "strokeRect");
    expect(rect?.style).toBe("#5b9cff");
    expect(rect?.arg).toEqual(expect.arrayContaining([expect.closeTo(r1.bbox.minX - 4 / base.viewport.scale, 6)]));
  });

  it("derives selectable sides from visible layers", () => {
    expect([...visibleSides(model, new Set(["F.Cu"]))]).toEqual(["top"]);
    expect(visibleSides(model, new Set(["Edge.Cuts"])).size).toBe(0);
  });
});
