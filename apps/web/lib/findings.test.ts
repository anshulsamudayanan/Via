import { describe, expect, it } from "vitest";

import { describeChange, findingHighlight, formatDelta, formatMetric, severityTone } from "./findings";

describe("finding helpers", () => {
  it("maps severities to tones", () => {
    expect(["critical", "high", "medium", "low", "info"].map((s) => severityTone(s as never))).toEqual(["danger", "danger", "warning", "neutral", "neutral"]);
  });

  it("builds a board highlight from a finding", () => {
    const bbox = { min_x: 1, min_y: 2, max_x: 3, max_y: 4 };
    const h = findingHighlight({ severity: "high", components: ["C1"], nets: ["GND", "SIG"], region: { bbox, points: [{ x: 2, y: 3 }], layers: ["F.Cu"] } });
    expect(h).toEqual({ references: ["C1"], nets: ["GND", "SIG"], regions: [{ bbox, severity: "high", points: [{ x: 2, y: 3 }] }], focus: true });
    expect(findingHighlight({ severity: "low", components: [], nets: [], region: null }).regions).toEqual([]);
  });

  it("formats metric values and deltas with units (lower is better)", () => {
    expect(formatDelta("board_area_mm2", -300)).toBe("−300 mm²");
    expect(formatDelta("manufacturing_issues", 2)).toBe("+2");
    expect(formatDelta("ratsnest_mm", 0)).toBe("0");
    expect(formatDelta("ratsnest_mm", null)).toBe("–");
    expect(formatMetric("board_area_mm2", 1200.04)).toBe("1200 mm²");
    expect(formatMetric("ratsnest_mm", 12.34567)).toBe("12.346 mm");
  });

  it("describes changes as before → after", () => {
    expect(describeChange("move_component", { x: 15, y: 5 }, { x: 18, y: 5 })).toBe("(15, 5) → (18, 5) mm");
    expect(describeChange("set_track_width", { width: 0.1 }, { width: 0.25 })).toBe("0.1 → 0.25 mm");
    expect(describeChange("set_via_size", { diameter: 0.6, drill: 0.3 }, { diameter: 0.8, drill: 0.4 })).toBe("⌀0.6/0.3 → ⌀0.8/0.4 mm");
    expect(describeChange("set_outline_rect", {}, { min_x: 0, min_y: 0, max_x: 30, max_y: 20 })).toBe("30 × 20 mm");
    expect(describeChange("rotate_component", { rotation: 0 }, { rotation: 90 })).toBe("0° → 90°");
  });
});
