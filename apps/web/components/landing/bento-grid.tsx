"use client";

/*
 * Bento grid of glass cards. Layout adapted from the 21st.dev "Bento Grid" (@my, karaui), surface
 * from the "Liquid Glass Card" candidate (designali-in): frosted glass, hairline, top highlight and a
 * cursor sheen. Cards blur-fade in on scroll (staggered) and lift with a slight scale on hover.
 */

import { cn, enter, enterReduced, Glass, SPRING, stagger, useHoverCapable } from "@via/ui";
import { m, useReducedMotion } from "motion/react";
import type { ReactNode } from "react";

type Span = 1 | 2 | 3;
const COL_SPAN: Record<Span, string> = { 1: "", 2: "@3xl:col-span-2", 3: "@3xl:col-span-3" };
const ROW_SPAN: Record<Span, string> = { 1: "", 2: "@3xl:row-span-2", 3: "@3xl:row-span-3" };

export function BentoGrid({ children, className }: { children: ReactNode; className?: string }) {
  return (
    <div className={cn("@container w-full", className)}>
      <m.ul
        initial="hidden"
        whileInView="show"
        viewport={{ once: true, amount: 0.12 }}
        variants={stagger(0.07)}
        className="grid grid-cols-1 gap-4 @3xl:auto-rows-[minmax(14rem,auto)] @3xl:grid-cols-3"
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
  return (
    <m.li
      variants={reduce ? enterReduced : enter}
      whileHover={canHover && !reduce ? { y: -4, scale: 1.01 } : undefined}
      transition={SPRING}
      className={cn("list-none", COL_SPAN[colSpan], ROW_SPAN[rowSpan], className)}
    >
      <Glass sheen className={cn("flex h-full flex-col overflow-hidden rounded-[26px] p-6", horizontal && "@3xl:flex-row-reverse @3xl:items-center @3xl:justify-end @3xl:gap-10")}>
        {visual ? (
          <div aria-hidden="true" className={cn("relative mb-6 flex min-h-28 flex-1 items-center justify-center", horizontal && "@3xl:mb-0 @3xl:min-h-0 @3xl:flex-none @3xl:justify-end")}>
            {visual}
          </div>
        ) : null}
        <div className={cn("mt-auto", horizontal && "@3xl:mt-0 @3xl:max-w-xl @3xl:flex-1")}>
          <div className="flex items-center gap-2.5">
            <span className="inline-flex size-8 shrink-0 items-center justify-center rounded-full bg-accent-soft text-accent ring-1 ring-accent-border [&_svg]:size-4">{icon}</span>
            <h3 className="text-[16px] font-semibold tracking-tight text-foreground">{title}</h3>
          </div>
          <p className="mt-2.5 text-[14px] leading-relaxed text-muted">{description}</p>
          {meta ? <p className="mt-3 font-mono text-[11px] text-subtle">{meta}</p> : null}
        </div>
      </Glass>
    </m.li>
  );
}
