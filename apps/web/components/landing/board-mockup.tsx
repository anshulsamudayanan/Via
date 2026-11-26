"use client";

import { cn } from "@via/ui";
import { AnimatePresence, m, useReducedMotion } from "motion/react";
import { useState } from "react";

/*
 * A stylized board viewer, drawn in SVG. It's an illustration (labelled as such for assistive tech):
 * the layer toggles work on the drawing, and the two DRC callouts show the shape of real findings.
 */

type Layer = "fcu" | "bcu" | "silk" | "edge";
const LAYERS: { id: Layer; label: string; swatch: string }[] = [
  { id: "fcu", label: "F.Cu", swatch: "bg-[var(--landing-copper)]" },
  { id: "bcu", label: "B.Cu", swatch: "bg-accent" },
  { id: "silk", label: "F.Silkscreen", swatch: "bg-foreground/70" },
  { id: "edge", label: "Edge.Cuts", swatch: "bg-warning" },
];

const FCU_TRACKS = [
  "M70 70 H150 L170 90 H214",
  "M70 96 H140 L160 116 H214",
  "M248 104 H300 L318 86 H344",
  "M248 122 H306 L330 146 V196",
  "M231 150 V200 L251 220 H300",
  "M110 200 H170 L190 180 V150 H214",
  "M70 200 H96",
];
const BCU_TRACKS = ["M120 60 V40 H290 L306 56 V86", "M84 150 V236 H230 L246 220", "M344 196 V236 H280"];
const VIAS: [number, number][] = [
  [120, 60], [306, 86], [84, 150], [246, 220], [344, 196], [280, 236],
];

function Pads({ x, y, n, horizontal, pitch = 10 }: { x: number; y: number; n: number; horizontal?: boolean; pitch?: number }) {
  return (
    <>
      {Array.from({ length: n }, (_, i) => (
        <rect
          key={i}
          x={horizontal ? x + i * pitch : x}
          y={horizontal ? y : y + i * pitch}
          width={horizontal ? 5 : 9}
          height={horizontal ? 9 : 5}
          rx={1}
        />
      ))}
    </>
  );
}

function Callout({ x, y, side, title, detail, delay, severity }: { x: number; y: number; side: "left" | "right"; title: string; detail: string; delay: number; severity: "high" | "low" }) {
  const reduce = useReducedMotion();
  return (
    <m.div
      initial={{ opacity: 0, y: reduce ? 0 : 6 }}
      animate={{ opacity: 1, y: 0 }}
      transition={{ delay, duration: 0.5, ease: [0.22, 1, 0.36, 1] }}
      className={cn("absolute z-10 w-[min(14rem,52%)]", side === "right" ? "translate-x-3" : "-translate-x-[calc(100%+0.75rem)]")}
      style={{ left: `${(x / 400) * 100}%`, top: `${(y / 280) * 100}%` }}
    >
      <div className={cn("rounded-md border bg-surface-raised/95 px-2.5 py-2 shadow-overlay backdrop-blur", severity === "high" ? "border-danger/40" : "border-border-strong")}>
        <p className="flex items-center gap-1.5 text-[11px] font-medium text-foreground">
          <span className={cn("rounded-sm px-1 text-[10px] font-semibold uppercase tracking-wide", severity === "high" ? "bg-danger-soft text-danger" : "bg-surface-hover text-muted")}>{severity}</span>
          {title}
        </p>
        <p className="mt-1 font-mono text-[10.5px] leading-snug text-muted">{detail}</p>
      </div>
    </m.div>
  );
}

export function BoardMockup() {
  const reduce = useReducedMotion();
  const [visible, setVisible] = useState<Record<Layer, boolean>>({ fcu: true, bcu: true, silk: true, edge: true });
  const fade = (on: boolean) => ({ opacity: on ? 1 : 0, transition: { duration: reduce ? 0 : 0.25 } });

  return (
    <figure
      aria-label="Illustration of the VIA board viewer: layer toggles and two design-rule findings on a board"
      className="relative overflow-hidden rounded-xl border border-border bg-surface/90 shadow-[0_30px_80px_-20px_var(--landing-glow)] backdrop-blur"
    >
      {/* Window chrome */}
      <div className="flex items-center gap-3 border-b border-border px-3 py-2">
        <span className="flex gap-1.5" aria-hidden="true">
          <span className="size-2.5 rounded-full bg-border-strong" />
          <span className="size-2.5 rounded-full bg-border-strong" />
          <span className="size-2.5 rounded-full bg-border-strong" />
        </span>
        <span className="truncate font-mono text-[11px] text-muted">
          motor_driver<span className="text-subtle">.kicad_pcb</span> <span className="text-subtle">· r2</span>
        </span>
        <span className="ml-auto inline-flex items-center gap-1.5 rounded-sm border border-border px-1.5 py-0.5 font-mono text-[10px] text-subtle">
          <span className="size-1.5 rounded-full bg-success" aria-hidden="true" /> parsed
        </span>
      </div>

      <div className="flex flex-col sm:flex-row">
        {/* Layer panel */}
        <div role="group" aria-label="Layers (illustration)" className="flex gap-1 border-b border-border p-2 sm:w-36 sm:flex-col sm:border-b-0 sm:border-r">
          <p className="hidden px-1.5 pb-1 text-[10px] font-medium uppercase tracking-[0.08em] text-subtle sm:block">Layers</p>
          {LAYERS.map((l) => (
            <button
              key={l.id}
              type="button"
              aria-pressed={visible[l.id]}
              onClick={() => setVisible((v) => ({ ...v, [l.id]: !v[l.id] }))}
              className={cn(
                "flex items-center gap-2 rounded-md px-1.5 py-1 text-left font-mono text-[11px] transition-colors duration-100 hover:bg-surface-hover",
                visible[l.id] ? "text-foreground" : "text-subtle line-through decoration-subtle/60",
              )}
            >
              <span className={cn("size-2.5 shrink-0 rounded-[2px] transition-opacity", l.swatch, !visible[l.id] && "opacity-30")} aria-hidden="true" />
              {l.label}
            </button>
          ))}
        </div>

        {/* Board */}
        <div className="relative flex-1 p-4 sm:p-6">
          <div className="relative">
            <svg viewBox="0 0 400 280" className="block h-auto w-full" aria-hidden="true">
              <defs>
                <pattern id="lm-grid" width="10" height="10" patternUnits="userSpaceOnUse">
                  <path d="M10 0H0V10" fill="none" stroke="var(--landing-grid)" strokeWidth="0.5" />
                </pattern>
                <clipPath id="lm-board">
                  <rect x="40" y="24" width="330" height="232" rx="10" />
                </clipPath>
              </defs>
              <rect width="400" height="280" fill="url(#lm-grid)" />
              <rect x="40" y="24" width="330" height="232" rx="10" fill="var(--landing-board)" />

              <g clipPath="url(#lm-board)">
                <m.g animate={fade(visible.bcu)} stroke="var(--via-accent)" strokeOpacity="0.55" strokeWidth="5" fill="none" strokeLinecap="round" strokeLinejoin="round">
                  {BCU_TRACKS.map((d) => (
                    <path key={d} d={d} />
                  ))}
                </m.g>
                <m.g animate={fade(visible.fcu)}>
                  <g stroke="var(--landing-copper)" strokeWidth="4" fill="none" strokeLinecap="round" strokeLinejoin="round">
                    {FCU_TRACKS.map((d) => (
                      <path key={d} d={d} />
                    ))}
                  </g>
                  <g fill="var(--landing-copper)">
                    {/* U1 (QFN), R1, R2, C1, J1 pads */}
                    <Pads x={214} y={86} n={6} pitch={8} />
                    <Pads x={239} y={86} n={6} pitch={8} />
                    <rect x={60} y={64} width={10} height={12} rx={1.5} />
                    <rect x={60} y={90} width={10} height={12} rx={1.5} />
                    <rect x={96} y={194} width={12} height={12} rx={1.5} />
                    <rect x={60} y={194} width={10} height={12} rx={1.5} />
                    <Pads x={226} y={150} n={1} />
                    <Pads x={290} y={214} n={3} horizontal pitch={14} />
                    <rect x={340} y={80} width={10} height={12} rx={1.5} />
                  </g>
                  <rect x={223} y={98} width={14} height={28} rx={1} fill="var(--landing-copper)" opacity="0.5" />
                </m.g>
                <m.g animate={fade(visible.fcu || visible.bcu)}>
                  {VIAS.map(([cx, cy]) => (
                    <g key={`${cx}-${cy}`}>
                      <circle cx={cx} cy={cy} r="5" fill="var(--landing-copper)" />
                      <circle cx={cx} cy={cy} r="2" fill="var(--landing-board)" />
                    </g>
                  ))}
                </m.g>
                <m.g animate={fade(visible.silk)} fill="none" stroke="var(--via-foreground)" strokeOpacity="0.55" strokeWidth="1">
                  <rect x="208" y="80" width="44" height="56" rx="2" />
                  <circle cx="213" cy="85" r="1.4" fill="var(--via-foreground)" />
                  <rect x="56" y="60" width="18" height="46" rx="2" />
                  <rect x="284" y="208" width="44" height="22" rx="2" />
                  <g fill="var(--via-foreground)" fillOpacity="0.6" stroke="none" fontFamily="var(--font-mono)" fontSize="8">
                    <text x="216" y="146">U1</text>
                    <text x="52" y="118">R1</text>
                    <text x="96" y="222">C1</text>
                    <text x="290" y="244">J1</text>
                  </g>
                </m.g>
              </g>
              <m.rect animate={fade(visible.edge)} x="40" y="24" width="330" height="232" rx="10" fill="none" stroke="var(--via-warning)" strokeWidth="1.5" />

              {/* Finding markers */}
              <g>
                <circle cx="171" cy="103" r="9" fill="none" stroke="var(--via-danger)" strokeWidth="1.5" />
                <circle cx="66" cy="96" r="9" fill="none" stroke="var(--via-muted)" strokeWidth="1.5" />
                {reduce ? null : (
                  <>
                    <circle cx="171" cy="103" r="9" fill="none" stroke="var(--via-danger)" className="origin-[171px_103px] animate-ping" style={{ animationDuration: "2.4s" }} />
                    <circle cx="66" cy="96" r="9" fill="none" stroke="var(--via-muted)" className="origin-[66px_96px] animate-ping" style={{ animationDuration: "2.4s", animationDelay: "1.2s" }} />
                  </>
                )}
              </g>
            </svg>

            {/* DRC scan line */}
            <div aria-hidden="true" className="landing-scan pointer-events-none absolute inset-x-[10%] top-0 h-[10%]">
              <div className="h-px w-full bg-accent shadow-[0_0_12px_2px_var(--landing-glow)]" />
              <div className="h-6 w-full bg-gradient-to-b from-[var(--landing-glow-soft)] to-transparent" />
            </div>

            <AnimatePresence>
              <Callout key="a" x={184} y={40} side="right" title="Copper spacing below 0.150 mm" detail="GND / SIG · smallest gap 0.118 mm" delay={0.9} severity="high" />
              <Callout key="b" x={78} y={150} side="right" title="Pad without net" detail="R1 pad 2 · F.Cu · no net assigned" delay={1.3} severity="low" />
            </AnimatePresence>
          </div>
        </div>
      </div>

      <figcaption className="flex items-center justify-between gap-3 border-t border-border px-3 py-1.5 font-mono text-[10.5px] text-subtle">
        <span>Illustration · toggle the layers</span>
        <span className="hidden sm:inline">2 findings · 1 high · 1 low</span>
      </figcaption>
    </figure>
  );
}
