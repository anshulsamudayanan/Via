"use client";

/*
 * The feature cards' mini-visuals. Decorative (the cards' text carries the meaning). They are static,
 * except the padlock, which clicks shut once when it scrolls into view (not under reduced motion).
 */

import { cn } from "@via/ui";
import { m, useInView, useReducedMotion } from "motion/react";
import { useRef } from "react";

export function ImportVisual() {
  return (
    <div className="flex w-full max-w-xs items-center gap-3 font-mono text-[11px]">
      <div className="flex flex-col gap-1.5">
        {[".kicad_pcb", ".zip", ".kicad_pro"].map((f) => (
          <span key={f} className="rounded-md border border-border bg-surface px-2.5 py-1 text-muted">
            {f}
          </span>
        ))}
      </div>
      <svg viewBox="0 0 60 60" className="h-14 w-10 shrink-0 text-subtle" fill="none">
        <path d="M2 10 C 30 10, 30 30, 58 30 M2 30 H58 M2 50 C 30 50, 30 30, 58 30" stroke="currentColor" strokeWidth="1.2" strokeOpacity="0.7" />
      </svg>
      <div className="flex-1 rounded-lg border border-border-strong bg-surface px-3 py-2 text-[11px] leading-relaxed text-muted">
        <span className="text-foreground">PCBDesign</span>
        <br />
        outline · layers · nets
        <br />
        footprints · pads · tracks
        <br />
        vias · zones
      </div>
    </div>
  );
}

export function ViewerVisual() {
  return (
    <svg viewBox="0 0 220 120" className="h-28 w-full max-w-[16rem]">
      <rect x="10" y="8" width="200" height="104" rx="10" fill="var(--landing-board)" stroke="var(--via-warning)" strokeOpacity="0.7" />
      <g stroke="var(--landing-copper)" strokeOpacity="0.35" strokeWidth="4" fill="none" strokeLinecap="round">
        <path d="M40 30 V20 H160 L176 36 V60" />
      </g>
      <g stroke="var(--landing-copper)" strokeWidth="3.5" fill="none" strokeLinecap="round" strokeLinejoin="round">
        <path d="M30 50 H90 L104 64 H130" />
        <path d="M30 72 H80 L96 88 H130" />
        <path d="M156 70 H190" />
      </g>
      <rect x="128" y="52" width="28" height="44" rx="3" fill="none" stroke="var(--via-silk)" strokeOpacity="0.6" />
      <rect x="126" y="58" width="32" height="32" rx="4" fill="none" stroke="var(--via-accent)" strokeWidth="1.5" strokeDasharray="3 3" />
      <text x="128" y="108" fontSize="8" fontFamily="var(--font-mono)" fill="var(--via-muted)">
        U1 · QFN-24
      </text>
    </svg>
  );
}

function useStarted() {
  const ref = useRef<HTMLDivElement>(null);
  const inView = useInView(ref, { once: true, amount: 0.5 });
  return [ref, inView] as const;
}

const REVS: [string, string][] = [
  ["r1", "imported"],
  ["r2", "change set applied · re-checked"],
  ["r3", "rolled back to r1"],
];

/** A revision history, newest last; the current revision is marked. */
export function RevisionsVisual() {
  const current = REVS.length - 1;
  return (
    <div className="relative flex w-full max-w-xs flex-col gap-2.5 font-mono text-[11px]">
      <span aria-hidden="true" className="absolute bottom-3 left-3 top-3 w-px bg-border-strong" />
      {REVS.map(([r, label], i) => {
        const on = i === current;
        return (
          <div key={r} className="relative flex items-center gap-2.5">
            <span className={cn("relative flex size-6 items-center justify-center rounded-full border bg-background", on ? "border-foreground/40 text-foreground" : "border-border-strong text-subtle")}>
              {r}
            </span>
            <span className={on ? "text-foreground" : "text-subtle"}>{label}</span>
          </div>
        );
      })}
    </div>
  );
}

/** A padlock whose shackle clicks shut, next to the access facts. */
export function PrivacyVisual() {
  const reduce = useReducedMotion();
  const [ref, inView] = useStarted();
  const shut = reduce || inView;
  return (
    <div ref={ref} className="flex items-center gap-4 font-mono text-[11px] text-muted">
      <span className="flex size-14 items-center justify-center rounded-2xl border border-border-strong bg-surface text-foreground">
        <svg viewBox="0 0 24 24" className="size-7" fill="none" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round">
          <m.path
            d="M7 11V7a5 5 0 0 1 10 0v4"
            initial={false}
            animate={{ y: shut ? 0 : -3, rotate: shut ? 0 : -14 }}
            style={{ transformOrigin: "17px 11px", transformBox: "view-box" }}
            transition={{ type: "spring", stiffness: 520, damping: 18, delay: reduce ? 0 : 0.5 }}
          />
          <rect x="4.5" y="11" width="15" height="10" rx="2.5" />
          <m.circle cx="12" cy="16" r="1.2" fill="currentColor" initial={false} animate={{ scale: shut ? [1, 1.6, 1] : 1 }} transition={{ delay: reduce ? 0 : 0.75, duration: 0.35 }} />
        </svg>
      </span>
      <div className="space-y-1">
        <p>
          visibility <span className="text-foreground">private</span>
        </p>
        <p>
          access <span className="text-foreground">checked server-side</span>
        </p>
        <p>
          others <span className="text-foreground">404</span>
        </p>
      </div>
    </div>
  );
}
