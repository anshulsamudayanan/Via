"use client";

/*
 * Adapted from the 21st.dev "How It Works" component (@chamaac): numbered steps joined by a
 * connector. The connector is a signal trace that draws in as the section scrolls through the
 * viewport (useScroll -> pathLength), and each step lights up when the trace reaches it.
 * Reduced motion: the trace is drawn and every step is lit.
 */

import { cn, Glass, SPRING } from "@via/ui";
import { m, useMotionValueEvent, useReducedMotion, useMotionValue, useScroll, useSpring } from "motion/react";
import { type ReactNode, useRef, useState } from "react";

export interface Step {
  title: string;
  body: ReactNode;
  /** Mono detail under the body: inputs or outputs of the step. */
  detail: string;
  icon: ReactNode;
}

export function HowItWorks({ steps }: { steps: Step[] }) {
  const reduce = useReducedMotion();
  const ref = useRef<HTMLOListElement>(null);
  const { scrollYProgress } = useScroll({ target: ref, offset: ["start 85%", "end 55%"] });
  // The trace only ever extends: scrolling back up doesn't un-draw it.
  const furthest = useMotionValue(reduce ? 1 : 0);
  const progress = useSpring(furthest, { stiffness: 200, damping: 30 });
  const [lit, setLit] = useState(reduce ? steps.length : 0);
  useMotionValueEvent(scrollYProgress, "change", (v) => {
    if (reduce) return;
    if (v > furthest.get()) furthest.set(v);
    setLit((l) => Math.max(l, Math.min(steps.length, Math.floor(v * steps.length + 0.35))));
  });
  const shown = reduce ? steps.length : lit;

  return (
    <ol ref={ref} className="relative grid gap-4 md:grid-cols-4 md:gap-5">
      {/* Connector: horizontal on desktop, vertical on mobile, behind the step nodes. */}
      <svg aria-hidden="true" className="pointer-events-none absolute left-[12.5%] top-[23px] hidden h-0.5 w-[75%] md:block" preserveAspectRatio="none" viewBox="0 0 100 2">
        <line x1="0" y1="1" x2="100" y2="1" stroke="var(--via-border-strong)" strokeWidth="2" vectorEffect="non-scaling-stroke" />
        <m.line x1="0" y1="1" x2="100" y2="1" stroke="var(--via-accent)" strokeWidth="2" vectorEffect="non-scaling-stroke" style={{ pathLength: progress }} />
      </svg>
      <svg aria-hidden="true" className="pointer-events-none absolute bottom-6 left-[23px] top-6 w-0.5 md:hidden" preserveAspectRatio="none" viewBox="0 0 2 100">
        <line x1="1" y1="0" x2="1" y2="100" stroke="var(--via-border-strong)" strokeWidth="2" vectorEffect="non-scaling-stroke" />
        <m.line x1="1" y1="0" x2="1" y2="100" stroke="var(--via-accent)" strokeWidth="2" vectorEffect="non-scaling-stroke" style={{ pathLength: progress }} />
      </svg>

      {steps.map((s, i) => {
        const on = i < shown;
        return (
          <li key={s.title} className="relative flex gap-4 md:flex-col md:gap-0">
            <m.span
              animate={{ scale: on ? 1 : 0.92 }}
              transition={SPRING}
              className={cn(
                "relative z-10 flex size-12 shrink-0 items-center justify-center rounded-full border transition-[color,background-color,border-color] duration-300 md:mx-auto [&_svg]:size-[18px]",
                on ? "border-accent-border bg-[color-mix(in_oklab,var(--via-background)_70%,var(--via-accent))] text-accent" : "border-border-strong bg-background text-subtle",
              )}
            >
              {s.icon}
            </m.span>
            <Glass variant="thin" className={cn("min-w-0 flex-1 rounded-3xl p-5 transition-opacity duration-300 md:mt-5", on ? "opacity-100" : "opacity-60")}>
              <p className={cn("font-mono text-[11px] transition-colors duration-300", on ? "text-accent" : "text-subtle")}>0{i + 1}</p>
              <h3 className="mt-1 text-[16px] font-semibold tracking-tight text-foreground">{s.title}</h3>
              <p className="mt-1.5 text-[14px] leading-relaxed text-muted">{s.body}</p>
              <p className="mt-3 font-mono text-[11px] leading-relaxed text-subtle">{s.detail}</p>
            </Glass>
          </li>
        );
      })}
    </ol>
  );
}
