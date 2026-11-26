"use client";

/*
 * Adapted from the 21st.dev "Bento Grid" component (@my, karaui): container-query grid, cards that
 * stagger in on scroll, and a cursor spotlight that lights the border. Restyled to VIA's tokens
 * (surface, border, accent), restrained radii, our focus ring, and no CTA links (features only).
 */

import { cn } from "@via/ui";
import { m, useMotionValue, useReducedMotion, type Variants } from "motion/react";
import { type MouseEvent, type ReactNode, useEffect, useState } from "react";

type Span = 1 | 2 | 3;
const COL_SPAN: Record<Span, string> = { 1: "", 2: "@3xl:col-span-2", 3: "@3xl:col-span-3" };
const ROW_SPAN: Record<Span, string> = { 1: "", 2: "@3xl:row-span-2", 3: "@3xl:row-span-3" };
const EASE_OUT = [0.22, 1, 0.36, 1] as const;
const SPOT = 320;

/** True only on devices with a real hover (no phantom hover on touch). */
function useHoverCapable() {
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

export function BentoGrid({ children, className }: { children: ReactNode; className?: string }) {
  return (
    <div className={cn("@container w-full", className)}>
      <m.ul
        initial="hidden"
        whileInView="show"
        viewport={{ once: true, amount: 0.15 }}
        variants={{ show: { transition: { staggerChildren: 0.07 } } }}
        className="grid grid-cols-1 gap-3 @3xl:auto-rows-[minmax(13rem,auto)] @3xl:grid-cols-3"
      >
        {children}
      </m.ul>
    </div>
  );
}

interface BentoCardProps {
  title: string;
  description: ReactNode;
  icon: ReactNode;
  /** Decorative illustration (aria-hidden). */
  visual?: ReactNode;
  /** Small mono label, e.g. the file types or check names. */
  meta?: ReactNode;
  colSpan?: Span;
  rowSpan?: Span;
  /** Visual beside the text (wide cards) instead of above it. */
  horizontal?: boolean;
  className?: string;
}

export function BentoCard({ title, description, icon, visual, meta, colSpan = 1, rowSpan = 1, horizontal = false, className }: BentoCardProps) {
  const reduce = useReducedMotion();
  const canHover = useHoverCapable();
  const [hovered, setHovered] = useState(false);
  const x = useMotionValue(-SPOT);
  const y = useMotionValue(-SPOT);

  function onMove(e: MouseEvent<HTMLElement>) {
    if (!canHover) return;
    const r = e.currentTarget.getBoundingClientRect();
    x.set(e.clientX - r.left - SPOT / 2);
    y.set(e.clientY - r.top - SPOT / 2);
  }

  const item: Variants = {
    hidden: { opacity: 0, y: reduce ? 0 : 16 },
    show: { opacity: 1, y: 0, transition: { duration: 0.5, ease: EASE_OUT } },
  };

  const spot = (cls: string) => (
    <m.span
      aria-hidden="true"
      style={{ x, y, width: SPOT, height: SPOT, background: "radial-gradient(circle closest-side, var(--via-accent), transparent)" }}
      className={cn("pointer-events-none absolute left-0 top-0 rounded-full", cls)}
    />
  );

  return (
    <m.li
      variants={item}
      onMouseMove={onMove}
      onMouseEnter={() => setHovered(true)}
      onMouseLeave={() => setHovered(false)}
      className={cn(
        "group/bento relative isolate flex flex-col overflow-hidden rounded-xl border border-border bg-surface/80 p-5 backdrop-blur-sm",
        horizontal && "@3xl:flex-row-reverse @3xl:items-center @3xl:justify-end @3xl:gap-10",
        COL_SPAN[colSpan],
        ROW_SPAN[rowSpan],
        className,
      )}
    >
      {canHover ? (
        <>
          <span aria-hidden="true" className={cn("pointer-events-none absolute inset-0 -z-10 overflow-hidden transition-opacity duration-300", hovered ? "opacity-[0.08]" : "opacity-0")}>
            {spot("")}
          </span>
          <span
            aria-hidden="true"
            className={cn(
              "pointer-events-none absolute inset-0 z-20 overflow-hidden rounded-[inherit] p-px transition-opacity duration-300 [mask-composite:exclude] [mask:linear-gradient(#000_0_0)_content-box,linear-gradient(#000_0_0)]",
              hovered ? "opacity-100" : "opacity-0",
            )}
          >
            {spot("opacity-70")}
          </span>
        </>
      ) : null}

      {visual ? (
        <div
          aria-hidden="true"
          className={cn(
            "relative mb-5 flex min-h-28 flex-1 items-center justify-center transition-transform duration-500 ease-[cubic-bezier(0.22,1,0.36,1)]",
            horizontal && "@3xl:mb-0 @3xl:min-h-0 @3xl:flex-none @3xl:justify-end",
            canHover && !reduce && "group-hover/bento:-translate-y-0.5",
          )}
        >
          {visual}
        </div>
      ) : null}

      <div className={cn("mt-auto", horizontal && "@3xl:mt-0 @3xl:max-w-xl @3xl:flex-1")}>
        <div className="flex items-center gap-2.5">
          <span className="inline-flex size-7 shrink-0 items-center justify-center rounded-md border border-border bg-surface-raised text-accent [&_svg]:size-3.5">{icon}</span>
          <h3 className="text-[15px] font-semibold leading-snug text-foreground">{title}</h3>
        </div>
        <p className="mt-2 text-[13px] leading-relaxed text-muted">{description}</p>
        {meta ? <p className="mt-3 font-mono text-[11px] text-subtle">{meta}</p> : null}
      </div>
    </m.li>
  );
}
