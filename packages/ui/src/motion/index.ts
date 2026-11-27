import type { Transition, Variants } from "motion/react";

/*
 * Motion tokens. Springs only (no linear easing): stiff and low-bounce, like iOS.
 * Components animate transform, opacity and filter only, never layout-affecting properties
 * (layout animations use Motion's `layout`, which also animates transforms).
 */
export const SPRING: Transition = { type: "spring", stiffness: 380, damping: 30, mass: 0.8 };
export const SPRING_SOFT: Transition = { type: "spring", stiffness: 300, damping: 30 };
export const SPRING_PRESS: Transition = { type: "spring", stiffness: 500, damping: 30 };

/** Entrance: a short fade and an 8px rise. Once per view, for the main content only. */
export const enter: Variants = {
  hidden: { opacity: 0, y: 8 },
  show: { opacity: 1, y: 0, transition: SPRING_SOFT },
};

/** Parent that staggers `enter` children. */
export const stagger = (gap = 0.06, delay = 0): Variants => ({
  hidden: {},
  show: { transition: { staggerChildren: gap, delayChildren: delay } },
});

/** Reduced motion: keep a plain fade, drop movement. */
export const enterReduced: Variants = {
  hidden: { opacity: 0 },
  show: { opacity: 1, transition: { duration: 0.2 } },
};
