"use client";

/*
 * Adapted from the 21st.dev "How It Works" component (@chamaac): numbered steps joined by a
 * connector, drawn as a quiet signal trace. Static: the steps are a sequence, not an animation.
 */

import { Glass } from "@via/ui";
import type { ReactNode } from "react";

export interface Step {
  title: string;
  body: ReactNode;
  /** Mono detail under the body: inputs or outputs of the step. */
  detail: string;
  icon: ReactNode;
}

export function HowItWorks({ steps }: { steps: Step[] }) {
  return (
    <ol className="relative grid gap-4 md:grid-cols-4 md:gap-5">
      {/* Connector: horizontal on desktop, vertical on mobile, behind the step nodes. */}
      <span aria-hidden="true" className="pointer-events-none absolute left-[12.5%] top-[23px] hidden h-px w-[75%] bg-border-strong md:block" />
      <span aria-hidden="true" className="pointer-events-none absolute bottom-6 left-[23px] top-6 w-px bg-border-strong md:hidden" />

      {steps.map((s, i) => (
        <li key={s.title} className="relative flex gap-4 md:flex-col md:gap-0">
          <span className="relative z-10 flex size-12 shrink-0 items-center justify-center rounded-full border border-border-strong bg-background text-muted md:mx-auto [&_svg]:size-[18px]">
            {s.icon}
          </span>
          <Glass variant="thin" className="min-w-0 flex-1 rounded-3xl p-5 md:mt-5">
            <p className="font-mono text-[12px] tabular-nums text-subtle">0{i + 1}</p>
            <h3 className="mt-1 text-[16px] font-medium text-foreground">{s.title}</h3>
            <p className="mt-2 text-[14px] leading-relaxed text-muted">{s.body}</p>
            <p className="mt-3 font-mono text-[12px] leading-relaxed text-subtle">{s.detail}</p>
          </Glass>
        </li>
      ))}
    </ol>
  );
}
