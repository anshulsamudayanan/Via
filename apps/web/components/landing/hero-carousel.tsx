"use client";

/*
 * The hero's carousel card: three illustrations of what VIA shows (board viewer, findings,
 * revisions), switched by pill tabs (active pill slides on a shared layoutId) or automatically.
 * Pattern from the 21st.dev "Carousel" (appica-dev, progress variant): an "01 / 03" counter and
 * segmented progress bars. Slides cross-fade with a blur. Autoplay pauses while the card is hovered
 * or focused, and is off under reduced motion.
 */

import { cn, LiquidGlass, SPRING } from "@via/ui";
import { animate, AnimatePresence, m, useMotionValue, useReducedMotion, useTransform } from "motion/react";
import { type ReactNode, useEffect, useState } from "react";

import { BoardMockup } from "./board-mockup";
import { RevisionsVisual } from "./feature-visuals";

const DURATION = 6; // seconds per slide

function FindingsSlide() {
  const rows: [string, string, string, string][] = [
    ["high", "Copper spacing below 0.150 mm: GND / SIG", "mfg_copper_spacing", "bg-danger-soft text-danger"],
    ["medium", "+3V3 on F.Cu: tracks too narrow for 1.5 A", "track_current_capacity", "bg-warning-soft text-warning"],
    ["low", "R1: copper pad(s) without a net", "pads_without_net", "bg-surface-hover text-muted"],
  ];
  return (
    <div className="flex h-full flex-col justify-center gap-2 p-5">
      <p className="font-mono text-[10.5px] uppercase tracking-[0.12em] text-subtle">Example findings</p>
      {rows.map(([sev, title, check, tone]) => (
        <div key={check} className="rounded-2xl border border-border bg-surface px-3.5 py-2.5">
          <p className="flex items-center gap-2 text-[13px] font-medium text-foreground">
            <span className={cn("rounded-full px-2 py-px text-[10px] font-semibold uppercase tracking-wide", tone)}>{sev}</span>
            <span className="truncate">{title}</span>
          </p>
          <p className="mt-1 font-mono text-[11px] text-subtle">{check} · measured vs rule · objects named</p>
        </div>
      ))}
    </div>
  );
}

function RevisionsSlide() {
  return (
    <div className="flex h-full flex-col justify-center gap-5 p-6">
      <p className="font-mono text-[10.5px] uppercase tracking-[0.12em] text-subtle">Revision history</p>
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
  const reduce = useReducedMotion();
  const [index, setIndex] = useState(0);
  const [paused, setPaused] = useState(false);
  const progress = useMotionValue(0);
  const fill = useTransform(progress, (v) => `scaleX(${v})`);

  // Autoplay: the active bar fills over DURATION, then the next slide shows. Resumes where it was.
  useEffect(() => {
    if (reduce || paused) return;
    const controls = animate(progress, 1, {
      duration: DURATION * (1 - progress.get()),
      ease: "linear", // a progress bar must track time evenly
      onComplete: () => {
        progress.set(0);
        setIndex((i) => (i + 1) % SLIDES.length);
      },
    });
    return () => controls.stop();
  }, [index, paused, reduce, progress]);

  function go(i: number) {
    progress.set(0);
    setIndex(i);
  }

  const slide = SLIDES[index]!;
  return (
    <LiquidGlass
      variant="regular"
      as="section"
      aria-roledescription="carousel"
      aria-label="What VIA shows"
      className="overflow-hidden rounded-[28px]"
      onMouseEnter={() => setPaused(true)}
      onMouseLeave={() => setPaused(false)}
      onFocus={() => setPaused(true)}
      onBlur={() => setPaused(false)}
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
            onClick={() => go(i)}
            className={cn("relative isolate rounded-full px-3.5 py-1.5 text-[13px] font-medium transition-colors", i === index ? "text-background" : "text-muted hover:text-foreground")}
          >
            {i === index ? <m.span layoutId="hero-tab-pill" transition={SPRING} aria-hidden="true" className="absolute inset-0 -z-10 rounded-full bg-foreground" /> : null}
            {s.tab}
          </button>
        ))}
      </div>

      {/* Slide */}
      <div id="hero-slide" role="tabpanel" aria-labelledby={`hero-tab-${slide.id}`} className="relative h-[380px] sm:h-[400px]">
        <AnimatePresence initial={false} mode="popLayout">
          <m.div
            key={slide.id}
            initial={reduce ? { opacity: 0 } : { opacity: 0, filter: "blur(8px)", scale: 0.985 }}
            animate={{ opacity: 1, filter: "blur(0px)", scale: 1 }}
            exit={reduce ? { opacity: 0 } : { opacity: 0, filter: "blur(8px)", scale: 1.01 }}
            transition={SPRING}
            className="absolute inset-0 overflow-hidden"
          >
            {slide.body}
          </m.div>
        </AnimatePresence>
      </div>

      {/* Caption, counter, segmented progress */}
      <div className="border-t border-border bg-[var(--via-scrim)] px-5 pb-4 pt-3">
        <p className="font-mono text-[12px] text-muted" aria-live="polite">
          <span className="text-foreground">{String(index + 1).padStart(2, "0")}</span> / {String(SLIDES.length).padStart(2, "0")}
        </p>
        <p className="mt-1 font-display text-[19px] font-semibold tracking-[-0.02em] text-foreground">{slide.title}</p>
        <p className="mt-0.5 text-[13px] text-muted">{slide.caption}</p>
        <div className="mt-3 flex gap-1.5" aria-hidden="true">
          {SLIDES.map((s, i) => (
            <span key={s.id} className="h-[3px] flex-1 overflow-hidden rounded-full bg-border-strong">
              {i < index || (reduce && i === index) ? (
                <span className="block h-full w-full bg-foreground" />
              ) : i === index ? (
                <m.span className="block h-full w-full origin-left bg-foreground" style={{ transform: fill }} />
              ) : null}
            </span>
          ))}
        </div>
      </div>
    </LiquidGlass>
  );
}
