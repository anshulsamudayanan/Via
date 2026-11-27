"use client";

import { Ambient, ToastProvider, TooltipProvider } from "@via/ui";
import { domMax, LazyMotion, MotionConfig } from "motion/react";
import { type ReactNode, useEffect } from "react";

/**
 * App-wide providers. Motion: `domMax` (layout and shared-layout animations), `strict` so only the
 * lightweight `m` components are used, and reducedMotion="user" so transform animations stop for
 * people who ask for less motion (components also check useReducedMotion for loops and parallax).
 */
/** Chromium renders SVG filters inside backdrop-filter; elsewhere one url() would void the blur. */
function useRefractionSupport() {
  useEffect(() => {
    const brands = (navigator as Navigator & { userAgentData?: { brands?: { brand: string }[] } }).userAgentData?.brands ?? [];
    if (brands.some((b) => b.brand === "Chromium")) document.documentElement.dataset.refraction = "";
  }, []);
}

/**
 * The liquid-glass edge refraction: low-frequency turbulence displaces what the thick glass shows,
 * strongest at a few pixels, so edges bend like a lens while the centre stays readable.
 */
function RefractionFilter() {
  return (
    <svg aria-hidden="true" width="0" height="0" className="pointer-events-none absolute">
      <filter id="via-refraction" x="0" y="0" width="100%" height="100%" colorInterpolationFilters="sRGB">
        <feTurbulence type="fractalNoise" baseFrequency="0.008 0.012" numOctaves="2" seed="7" result="noise" />
        <feGaussianBlur in="noise" stdDeviation="2" result="soft" />
        <feDisplacementMap in="SourceGraphic" in2="soft" scale="18" xChannelSelector="R" yChannelSelector="G" />
      </filter>
    </svg>
  );
}

export function Providers({ children }: { children: ReactNode }) {
  useRefractionSupport();
  return (
    <MotionConfig reducedMotion="user">
      <LazyMotion features={domMax} strict>
        <TooltipProvider>
          <ToastProvider>
            <Ambient />
            <RefractionFilter />
            {children}
          </ToastProvider>
        </TooltipProvider>
      </LazyMotion>
    </MotionConfig>
  );
}
