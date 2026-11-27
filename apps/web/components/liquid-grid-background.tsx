"use client";

import { cn } from "@via/ui";
import { useReducedMotion } from "motion/react";
import { type ComponentProps, useEffect, useRef, useState } from "react";

import LiquidGrid from "@/components/originkit/liquid-grid";
import { useTheme } from "@/lib/use-theme";

type GridProps = Omit<ComponentProps<typeof LiquidGrid>, "style" | "lineColor" | "glowColor" | "background">;

/**
 * Originkit's Liquid Grid as a decorative background (one per view). The grid itself is untouched;
 * this wrapper adds what a page background needs:
 * - the animated canvas only runs while the area is on screen and the tab is visible
 *   (IntersectionObserver + visibilitychange); otherwise a static grid stands in;
 * - prefers-reduced-motion always gets the static grid;
 * - colours follow the theme (faint white dots and a purple glow on dark, the inverse on light).
 * DPR is already capped at 2 inside the grid.
 */
export function LiquidGridBackground({ className, cellSize = 22, opacity = 1, ...grid }: GridProps & { className?: string; opacity?: number }) {
  const ref = useRef<HTMLDivElement>(null);
  const reduce = useReducedMotion();
  const theme = useTheme();
  const [onScreen, setOnScreen] = useState(false);
  const [tabVisible, setTabVisible] = useState(true);

  useEffect(() => {
    const el = ref.current;
    if (!el) return;
    const io = new IntersectionObserver(([e]) => setOnScreen(Boolean(e?.isIntersecting)), { rootMargin: "100px" });
    io.observe(el);
    const onVis = () => setTabVisible(document.visibilityState === "visible");
    onVis();
    document.addEventListener("visibilitychange", onVis);
    return () => {
      io.disconnect();
      document.removeEventListener("visibilitychange", onVis);
    };
  }, []);

  const dark = theme !== "light";
  const lineColor = dark ? "rgba(255, 255, 255, 0.07)" : "rgba(10, 10, 20, 0.09)";
  const glowColor = dark ? "#ad9be4" : "#5e4d93";
  const live = onScreen && tabVisible && !reduce;

  return (
    <div ref={ref} aria-hidden="true" className={cn("pointer-events-none absolute inset-0 overflow-hidden", className)} style={{ opacity }}>
      {live ? (
        <LiquidGrid mode="dots" background="rgba(0,0,0,0)" lineColor={lineColor} glowColor={glowColor} cellSize={cellSize} {...grid} />
      ) : (
        // Static stand-in: the same dot lattice, no motion.
        <div
          className="size-full"
          style={{ backgroundImage: `radial-gradient(circle, ${lineColor} 1px, transparent 1.4px)`, backgroundSize: `${cellSize}px ${cellSize}px` }}
        />
      )}
    </div>
  );
}
