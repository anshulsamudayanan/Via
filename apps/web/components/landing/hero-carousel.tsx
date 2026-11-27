"use client";

/*
 * The hero's product card: three illustrations of what VIA shows (board viewer, findings,
 * revisions), switched by tabs (the active tab's fill slides on a shared layoutId). Slides only
 * change when the visitor picks a tab, with a short cross-fade.
 */

import { cn, LiquidGlass, SPRING } from "@via/ui";
import { AnimatePresence, m } from "motion/react";
import { type ReactNode, useState } from "react";

import { BoardMockup } from "./board-mockup";
import { RevisionsVisual } from "./feature-visuals";

function FindingsSlide() {
  const rows: [string, string, string, string][] = [
    ["High", "Copper spacing below 0.150 mm: GND / SIG", "mfg_copper_spacing", "text-danger"],
    ["Medium", "+3V3 on F.Cu: tracks too narrow for 1.5 A", "track_current_capacity", "text-warning"],
    ["Low", "R1: copper pad(s) without a net", "pads_without_net", "text-muted"],
  ];
  return (
    <div className="flex h-full flex-col justify-center gap-2 p-5">
      <p className="text-[12px] text-subtle">Example findings</p>
      {rows.map(([sev, title, check, tone]) => (
        <div key={check} className="rounded-xl border border-border bg-surface px-3.5 py-2.5">
          <p className="flex items-center gap-2 text-[13px] font-medium text-foreground">
            <span className={cn("w-14 shrink-0 text-[12px]", tone)}>{sev}</span>
            <span className="truncate">{title}</span>
          </p>
          <p className="mt-1 pl-16 font-mono text-[11px] text-subtle">{check} · measured vs rule · objects named</p>
        </div>
      ))}
    </div>
  );
}

function RevisionsSlide() {
  return (
    <div className="flex h-full flex-col justify-center gap-5 p-6">
      <p className="text-[12px] text-subtle">Revision history</p>
      <RevisionsVisual />
      <p className="max-w-xs text-[13px] leading-relaxed text-muted">A change set is applied, the checks run again, and the result is kept as a new revision.</p>
    </div>
  );
}

interface Slide {
  id: string;
  tab: string;
  title: string;
  caption: string;
  body: ReactNode;
}

const SLIDES: Slide[] = [
  { id: "viewer", tab: "Board viewer", title: "Board viewer", caption: "The real parsed board: layers, components, findings on the copper.", body: <BoardMockup frame="none" /> },
  { id: "findings", tab: "Findings", title: "Evidence-backed findings", caption: "Each finding names its check, the objects and the measured value.", body: <FindingsSlide /> },
  { id: "revisions", tab: "Revisions", title: "Validated revisions", caption: "Compare, download or roll back any revision.", body: <RevisionsSlide /> },
];

export function HeroCarousel() {
  const [index, setIndex] = useState(0);

  const slide = SLIDES[index]!;
  return (
    <LiquidGlass
      variant="regular"
      as="section"
      aria-roledescription="carousel"
      aria-label="What VIA shows"
      className="@container overflow-hidden rounded-3xl"
    >
      {/* Tabs */}
      <div role="tablist" aria-label="Choose a view" className="flex gap-1 border-b border-border p-2">
        {SLIDES.map((s, i) => (
          <button
            key={s.id}
            type="button"
            role="tab"
            id={`hero-tab-${s.id}`}
            aria-selected={i === index}
            aria-controls="hero-slide"
            onClick={() => setIndex(i)}
            className={cn("relative isolate rounded-full px-3.5 py-1.5 text-[13px] font-medium transition-colors", i === index ? "text-background" : "text-muted hover:text-foreground")}
          >
            {i === index ? <m.span layoutId="hero-tab-pill" transition={SPRING} aria-hidden="true" className="absolute inset-0 -z-10 rounded-full bg-foreground" /> : null}
            {s.tab}
          </button>
        ))}
      </div>

      {/* Slide */}
      <div id="hero-slide" role="tabpanel" aria-labelledby={`hero-tab-${slide.id}`} className="relative h-[max(380px,calc(96px+70cqw))]">
        <AnimatePresence initial={false} mode="popLayout">
          <m.div
            key={slide.id}
            initial={{ opacity: 0 }}
            animate={{ opacity: 1 }}
            exit={{ opacity: 0 }}
            transition={{ duration: 0.18 }}
            className="absolute inset-0 overflow-hidden"
          >
            {slide.body}
          </m.div>
        </AnimatePresence>
      </div>

      {/* Caption */}
      <div className="border-t border-border bg-[var(--via-scrim)] px-5 py-4">
        <p className="text-[15px] font-medium text-foreground" aria-live="polite">
          {slide.title}
        </p>
        <p className="mt-1 text-[13px] text-muted">{slide.caption}</p>
      </div>
    </LiquidGlass>
  );
}
