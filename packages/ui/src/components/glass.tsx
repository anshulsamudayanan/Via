"use client";

import { m, useMotionTemplate, useMotionValue, useReducedMotion } from "motion/react";
import { type HTMLAttributes, type MouseEvent, type ReactNode, useEffect, useState } from "react";

import { cn } from "../cn";

export type GlassVariant = "thin" | "regular" | "thick" | "overlay";

const VARIANT: Record<GlassVariant, string> = { thin: "glass-thin", regular: "glass-regular", thick: "glass-thick", overlay: "glass-overlay" };

/** True only on devices with a real hover (no phantom hover on touch). */
export function useHoverCapable() {
  const [can, setCan] = useState(false);
  useEffect(() => {
    const mq = window.matchMedia("(hover: hover) and (pointer: fine)");
    const update = () => setCan(mq.matches);
    update();
    mq.addEventListener("change", update);
    return () => mq.removeEventListener("change", update);
  }, []);
  return can;
}

interface GlassProps extends HTMLAttributes<HTMLDivElement> {
  variant?: GlassVariant;
  /** A specular highlight that follows the cursor (hover-capable devices only). */
  sheen?: boolean;
  /** Render as another element, e.g. "section" or "li". */
  as?: "div" | "section" | "li" | "aside" | "header" | "article" | "figure";
  children?: ReactNode;
}

/**
 * Liquid glass surface (VIA's <LiquidGlass>): translucent fill, blur + saturate + brightness,
 * specular gradient rim, inner highlight and shadow, soft outer shadow, optional cursor sheen. The
 * recipe lives in styles.css (.glass-thin / -regular / -thick / -overlay); thick also refracts its
 * edges on Chromium.
 */
export function LiquidGlass({ variant = "regular", sheen = false, as: Tag = "div", className, children, onMouseMove, ...props }: GlassProps) {
  const canHover = useHoverCapable();
  const reduce = useReducedMotion();
  const x = useMotionValue(-400);
  const y = useMotionValue(-400);
  const background = useMotionTemplate`radial-gradient(260px circle at ${x}px ${y}px, var(--via-glass-sheen), transparent 70%)`;
  const live = sheen && canHover && !reduce;

  function move(e: MouseEvent<HTMLDivElement>) {
    if (live) {
      const r = e.currentTarget.getBoundingClientRect();
      x.set(e.clientX - r.left);
      y.set(e.clientY - r.top);
    }
    onMouseMove?.(e);
  }

  return (
    <Tag
      className={cn("group/glass relative isolate", VARIANT[variant], className)}
      onMouseMove={move as never}
      onMouseLeave={live ? () => (x.set(-400), y.set(-400)) : undefined}
      {...(props as HTMLAttributes<HTMLElement>)}
    >
      {live ? <m.span aria-hidden="true" style={{ background }} className="pointer-events-none absolute inset-0 -z-10 rounded-[inherit]" /> : null}
      {children}
    </Tag>
  );
}

/** @deprecated name kept for existing call sites; same component as LiquidGlass. */
export const Glass = LiquidGlass;
