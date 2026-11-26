/**
 * Layer colours for the board viewer.
 *
 * This is a data-visualization palette (one hue per PCB layer), the one place in
 * the web app where raw colours are allowed (see CLAUDE.md "Frontend"). Each
 * entry has a dark- and light-theme value; hues follow common EDA conventions
 * (front copper red, back copper blue, board edge yellow).
 */

import type { LayerKind, Side } from "@via/types";

export type Theme = "dark" | "light";

export interface ViewerColors {
  background: string;
  board: string;
  via: string;
  hole: string;
  selection: string;
  selectionFill: string;
  /** Highlighted nets and components (findings, search). */
  highlight: string;
  highlightFill: string;
  /** Finding regions by severity. */
  severity: Record<"critical" | "high" | "medium" | "low" | "info", string>;
}

export const VIEWER_COLORS: Record<Theme, ViewerColors> = {
  dark: {
    background: "#0a0c0f", board: "#10161c", via: "#c9ced6", hole: "#0a0c0f", selection: "#5b9cff", selectionFill: "rgba(91,156,255,0.12)",
    highlight: "#ffd84a", highlightFill: "rgba(255,216,74,0.16)",
    severity: { critical: "#ff4d5e", high: "#ff8a3d", medium: "#f2c94c", low: "#5bc0eb", info: "#9aa4b2" },
  },
  light: {
    background: "#f4f5f7", board: "#e9edf1", via: "#5c6470", hole: "#f4f5f7", selection: "#2563eb", selectionFill: "rgba(37,99,235,0.10)",
    highlight: "#b7791f", highlightFill: "rgba(183,121,31,0.14)",
    severity: { critical: "#c81e3a", high: "#c2410c", medium: "#a16207", low: "#0369a1", info: "#4b5563" },
  },
};

const INNER = {
  dark: ["#d4b13f", "#3fae72", "#a77bd6", "#36b4bd", "#d68a3f", "#7fbf3f"],
  light: ["#a38216", "#1f8a52", "#7d4fb3", "#14858d", "#b0661c", "#5c9220"],
};

export function layerColor(name: string, kind: LayerKind, side: Side, innerIndex: number, theme: Theme): string {
  const dark = theme === "dark";
  switch (kind) {
    case "copper":
      if (side === "top") return dark ? "#d2504f" : "#c0392b";
      if (side === "bottom") return dark ? "#4d86d9" : "#2a62b8";
      return INNER[theme][innerIndex % INNER[theme].length]!;
    case "silkscreen":
      return side === "bottom" ? (dark ? "#b49cd9" : "#7b5ea7") : dark ? "#e8e8e8" : "#2c2c2c";
    case "edge":
      return dark ? "#e8c547" : "#b8900b";
    case "solder_mask":
      return side === "bottom" ? (dark ? "#3f8f8f" : "#2d7070") : dark ? "#a54d86" : "#8c3a70";
    case "solder_paste":
      return dark ? "#9aa0a8" : "#6b717a";
    case "fabrication":
      return side === "bottom" ? (dark ? "#7f86a8" : "#5a6185") : dark ? "#a8a8a8" : "#6f6f6f";
    case "courtyard":
      return side === "bottom" ? (dark ? "#5fae9e" : "#2f8a78") : dark ? "#8fcf5f" : "#4c8f1f";
    default:
      return name.startsWith("B.") ? (dark ? "#8a93a6" : "#5d6577") : dark ? "#9fb3c8" : "#56708a";
  }
}
