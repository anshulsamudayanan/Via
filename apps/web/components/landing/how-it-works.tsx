"use client";

/*
 * Adapted from the 21st.dev "How It Works" component (@chamaac): numbered cards joined by an
 * animated dashed connector. Rebuilt as a straight trace (no rotated "pinned" cards or handwriting
 * font) so it reads as a signal path; the dashes march only without reduced motion.
 */

import { m, useReducedMotion } from "motion/react";
import type { ReactNode } from "react";

export interface Step {
  title: string;
  body: ReactNode;
  /** Mono detail under the body: inputs or outputs of the step. */
  detail: string;
  icon: ReactNode;
}

export function HowItWorks({ steps }: { steps: Step[] }) {
  const reduce = useReducedMotion();
  return (
    <ol className="relative grid gap-4 md:grid-cols-4 md:gap-5">
      {/* Connector: horizontal on desktop, vertical on mobile, behind the step nodes. */}
      <svg aria-hidden="true" className="pointer-events-none absolute left-[12.5%] top-[21px] hidden h-0.5 w-[75%] md:block" preserveAspectRatio="none" viewBox="0 0 100 2">
        <line x1="0" y1="1" x2="100" y2="1" stroke="var(--via-border-strong)" strokeWidth="2" vectorEffect="non-scaling-stroke" />
        <line x1="0" y1="1" x2="100" y2="1" stroke="var(--via-accent)" strokeWidth="2" vectorEffect="non-scaling-stroke" className={reduce ? undefined : "landing-march"} strokeDasharray={reduce ? "6 8" : undefined} />
      </svg>
      <span aria-hidden="true" className="absolute bottom-6 left-[22px] top-6 w-px bg-border-strong md:hidden" />

      {steps.map((s, i) => (
        <m.li
          key={s.title}
          initial={{ opacity: 0, y: reduce ? 0 : 14 }}
          whileInView={{ opacity: 1, y: 0 }}
          viewport={{ once: true, amount: 0.4 }}
          transition={{ delay: i * 0.1, duration: 0.5, ease: [0.22, 1, 0.36, 1] }}
          className="relative flex gap-4 md:flex-col md:gap-0"
        >
          <span className="relative z-10 flex size-11 shrink-0 items-center justify-center rounded-full border border-border-strong bg-surface text-accent shadow-[0_0_0_6px_var(--via-background)] md:mx-auto [&_svg]:size-4">
            {s.icon}
          </span>
          <div className="min-w-0 flex-1 rounded-xl border border-border bg-surface/70 p-4 backdrop-blur-sm md:mt-5">
            <p className="font-mono text-[11px] text-subtle">0{i + 1}</p>
            <h3 className="mt-1 text-[15px] font-semibold text-foreground">{s.title}</h3>
            <p className="mt-1.5 text-[13px] leading-relaxed text-muted">{s.body}</p>
            <p className="mt-3 font-mono text-[11px] leading-relaxed text-subtle">{s.detail}</p>
          </div>
        </m.li>
      ))}
    </ol>
  );
}
