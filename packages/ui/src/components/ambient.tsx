"use client";

import { m, useReducedMotion, useScroll, useTransform } from "motion/react";

/**
 * The light behind the glass: soft colour fields (violet from the accent, indigo, a touch of teal
 * and blue) drifting slowly, with gentle scroll parallax, plus film grain. One fixed layer for the whole
 * page; radial gradients rather than filter blur, so it costs almost nothing to composite.
 * Reduced motion: static.
 */
export function Ambient() {
  const reduce = useReducedMotion();
  const { scrollY } = useScroll();
  const slow = useTransform(scrollY, [0, 2000], [0, reduce ? 0 : -160]);
  const slower = useTransform(scrollY, [0, 2000], [0, reduce ? 0 : -80]);

  const drift = (dx: number, dy: number, duration: number) =>
    reduce ? undefined : { x: [0, dx, -dx * 0.6, 0], y: [0, dy, dy * 0.4, 0], transition: { duration, repeat: Infinity, ease: "easeInOut" as const } };

  return (
    <div aria-hidden="true" className="pointer-events-none fixed inset-0 -z-50 overflow-hidden bg-background">
      <m.div style={{ y: slow }} className="absolute inset-0">
        <m.div
          animate={drift(80, 40, 70)}
          className="absolute -left-[10%] -top-[15%] size-[70vmax] rounded-full"
          style={{ background: "radial-gradient(closest-side, var(--via-blob-violet), transparent)" }}
        />
        <m.div
          animate={drift(-70, 60, 90)}
          className="absolute -right-[20%] top-[10%] size-[60vmax] rounded-full"
          style={{ background: "radial-gradient(closest-side, var(--via-blob-indigo), transparent)" }}
        />
      </m.div>
      <m.div style={{ y: slower }} className="absolute inset-0">
        <m.div
          animate={drift(60, -50, 80)}
          className="absolute -bottom-[25%] left-[20%] size-[55vmax] rounded-full"
          style={{ background: "radial-gradient(closest-side, var(--via-blob-blue), transparent)" }}
        />
        <m.div
          animate={drift(-50, -40, 100)}
          className="absolute -bottom-[10%] -right-[10%] size-[45vmax] rounded-full"
          style={{ background: "radial-gradient(closest-side, var(--via-blob-teal), transparent)" }}
        />
      </m.div>
      <div className="via-grain absolute inset-0" />
    </div>
  );
}
