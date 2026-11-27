"use client";

import { Ambient, ToastProvider, TooltipProvider } from "@via/ui";
import { domMax, LazyMotion, MotionConfig } from "motion/react";
import type { ReactNode } from "react";

/**
 * App-wide providers. Motion: `domMax` (layout and shared-layout animations), `strict` so only the
 * lightweight `m` components are used, and reducedMotion="user" so transform animations stop for
 * people who ask for less motion (components also check useReducedMotion for loops and parallax).
 */
export function Providers({ children }: { children: ReactNode }) {
  return (
    <MotionConfig reducedMotion="user">
      <LazyMotion features={domMax} strict>
        <TooltipProvider>
          <ToastProvider>
            <Ambient />
            {children}
          </ToastProvider>
        </TooltipProvider>
      </LazyMotion>
    </MotionConfig>
  );
}
