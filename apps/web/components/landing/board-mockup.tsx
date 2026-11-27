"use client";

import { cn, Glass, useHoverCapable } from "@via/ui";
import { AnimatePresence, m, useMotionValue, useReducedMotion, useSpring, useTransform } from "motion/react";
import { type MouseEvent, useState } from "react";

/*
 * A stylized board viewer, drawn in SVG, on a glass panel. It's an illustration (labelled as such for
 * assistive tech): the layer toggles work on the drawing, and the two DRC callouts show the shape of
 * real findings. Motion: a slight 3D tilt toward the cursor (motion values -> springs -> transforms),
 * traces "route" in with pathLength, and the callouts pop in one after another as glass chips.
 * Reduced motion: no tilt, no drawing, no pulse; everything is simply shown.
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
const ROUTE = { type: "spring", stiffness: 40, damping: 16 } as const;

function Pads({ x, y, n, horizontal, pitch = 10 }: { x: number; y: number; n: number; horizontal?: boolean; pitch?: number }) {
  return (
    <>
      {Array.from({ length: n }, (_, i) => (
        <rect key={i} x={horizontal ? x + i * pitch : x} y={horizontal ? y : y + i * pitch} width={horizontal ? 5 : 9} height={horizontal ? 9 : 5} rx={1} />
      ))}
    </>
  );
}

function Track({ d, i, reduce }: { d: string; i: number; reduce: boolean | null }) {
  return reduce ? (
    <path d={d} />
  ) : (
    <m.path d={d} initial={{ pathLength: 0 }} animate={{ pathLength: 1 }} transition={{ ...ROUTE, delay: 0.35 + i * 0.09 }} />
  );
}

function Callout({ x, y, title, detail, delay, severity }: { x: number; y: number; title: string; detail: string; delay: number; severity: "high" | "low" }) {
  const reduce = useReducedMotion();
  return (
    <m.div
      initial={reduce ? { opacity: 0 } : { opacity: 0, scale: 0.85, y: 6, filter: "blur(6px)" }}
      animate={{ opacity: 1, scale: 1, y: 0, filter: "blur(0px)" }}
      transition={{ type: "spring", stiffness: 360, damping: 24, delay }}
      className="absolute z-10 w-[min(14rem,52%)] origin-left translate-x-3"
      style={{ left: `${(x / 400) * 100}%`, top: `${(y / 280) * 100}%` }}
    >
      <div className={cn("rounded-2xl border border-border-strong bg-[color-mix(in_oklab,var(--via-background)_90%,transparent)] px-3 py-2 shadow-overlay", severity === "high" ? "ring-1 ring-danger/35" : "")}>
        <p className="flex items-center gap-1.5 text-[11px] font-medium text-foreground">
          <span className={cn("rounded-full px-1.5 text-[10px] font-semibold uppercase tracking-wide", severity === "high" ? "bg-danger-soft text-danger" : "bg-surface-hover text-muted")}>{severity}</span>
          {title}
        </p>
        <p className="mt-1 font-mono text-[10.5px] leading-snug text-muted">{detail}</p>
      </div>
    </m.div>
  );
}

function Marker({ cx, cy, color, delay, reduce }: { cx: number; cy: number; color: string; delay: number; reduce: boolean | null }) {
  return (
    <>
      <circle cx={cx} cy={cy} r="9" fill="none" stroke={color} strokeWidth="1.5" />
      {reduce ? null : (
        <m.circle
          cx={cx}
          cy={cy}
          r="9"
          fill="none"
          stroke={color}
          style={{ transformOrigin: `${cx}px ${cy}px`, transformBox: "view-box" }}
          initial={{ scale: 1, opacity: 0.8 }}
          animate={{ scale: 2.2, opacity: 0 }}
          transition={{ duration: 2.2, repeat: Infinity, ease: "easeOut", delay }}
        />
      )}
    </>
  );
}

export function BoardMockup() {
  const reduce = useReducedMotion();
  const canHover = useHoverCapable();
  const [visible, setVisible] = useState<Record<Layer, boolean>>({ fcu: true, bcu: true, silk: true, edge: true });
  const fade = (on: boolean) => ({ opacity: on ? 1 : 0, transition: { type: "spring" as const, stiffness: 300, damping: 30 } });

  // Tilt: pointer position (-0.5..0.5) -> spring -> degrees.
  const px = useMotionValue(0);
  const py = useMotionValue(0);
  const sx = useSpring(px, { stiffness: 150, damping: 20 });
  const sy = useSpring(py, { stiffness: 150, damping: 20 });
  const rotateY = useTransform(sx, [-0.5, 0.5], [-6, 6]);
  const rotateX = useTransform(sy, [-0.5, 0.5], [5, -5]);
  const tilt = canHover && !reduce;

  function onMove(e: MouseEvent<HTMLDivElement>) {
    if (!tilt) return;
    const r = e.currentTarget.getBoundingClientRect();
    px.set((e.clientX - r.left) / r.width - 0.5);
    py.set((e.clientY - r.top) / r.height - 0.5);
  }

  return (
    <div
      className="[perspective:1400px]"
      onMouseMove={onMove}
      onMouseLeave={() => {
        px.set(0);
        py.set(0);
      }}
    >
      <m.div style={tilt ? { rotateX, rotateY, transformStyle: "preserve-3d" } : undefined}>
        <Glass
          as="figure"
          variant="regular"
          aria-label="Illustration of the VIA board viewer: layer toggles and two design-rule findings on a board"
          className="overflow-hidden rounded-[28px] shadow-[0_40px_120px_-30px_var(--landing-glow)]"
        >
          {/* Window chrome */}
          <div className="flex items-center gap-3 border-b border-border px-4 py-2.5">
            <span className="flex gap-1.5" aria-hidden="true">
              <span className="size-2.5 rounded-full bg-[#ff5f57]/80" />
              <span className="size-2.5 rounded-full bg-[#febc2e]/80" />
              <span className="size-2.5 rounded-full bg-[#28c840]/80" />
            </span>
            <span className="truncate font-mono text-[11px] text-muted">
              motor_driver<span className="text-subtle">.kicad_pcb</span> <span className="text-subtle">· r2</span>
            </span>
            <span className="ml-auto inline-flex items-center gap-1.5 rounded-full border border-border px-2 py-0.5 font-mono text-[10px] text-subtle">
              <span className="size-1.5 rounded-full bg-success" aria-hidden="true" /> parsed
            </span>
          </div>

          <div className="flex flex-col sm:flex-row">
            {/* Layer panel */}
            <div role="group" aria-label="Layers (illustration)" className="flex gap-1 overflow-x-auto border-b border-border p-2 sm:w-36 sm:flex-col sm:border-b-0 sm:border-r">
              <p className="hidden px-2 pb-1 text-[10px] font-medium uppercase tracking-[0.08em] text-subtle sm:block">Layers</p>
              {LAYERS.map((l) => (
                <button
                  key={l.id}
                  type="button"
                  aria-pressed={visible[l.id]}
                  onClick={() => setVisible((v) => ({ ...v, [l.id]: !v[l.id] }))}
                  className={cn(
                    "flex shrink-0 items-center gap-2 rounded-full px-2 py-1 text-left font-mono text-[11px] transition-colors duration-150 hover:bg-surface-hover",
                    visible[l.id] ? "text-foreground" : "text-subtle line-through decoration-subtle/60",
                  )}
                >
                  <span className={cn("size-2.5 shrink-0 rounded-full transition-opacity", l.swatch, !visible[l.id] && "opacity-30")} aria-hidden="true" />
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
                      <rect x="40" y="24" width="330" height="232" rx="12" />
                    </clipPath>
                  </defs>
                  <rect width="400" height="280" fill="url(#lm-grid)" />
                  <rect x="40" y="24" width="330" height="232" rx="12" fill="var(--landing-board)" />

                  <g clipPath="url(#lm-board)">
                    <m.g animate={fade(visible.bcu)} stroke="var(--via-accent)" strokeOpacity="0.6" strokeWidth="5" fill="none" strokeLinecap="round" strokeLinejoin="round">
                      {BCU_TRACKS.map((d, i) => (
                        <Track key={d} d={d} i={i + FCU_TRACKS.length} reduce={reduce} />
                      ))}
                    </m.g>
                    <m.g animate={fade(visible.fcu)}>
                      <g stroke="var(--landing-copper)" strokeWidth="4" fill="none" strokeLinecap="round" strokeLinejoin="round">
                        {FCU_TRACKS.map((d, i) => (
                          <Track key={d} d={d} i={i} reduce={reduce} />
                        ))}
                      </g>
                      <g fill="var(--landing-copper)">
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
                  <m.rect animate={fade(visible.edge)} x="40" y="24" width="330" height="232" rx="12" fill="none" stroke="var(--via-warning)" strokeWidth="1.5" />

                  {/* Finding markers */}
                  <Marker cx={171} cy={103} color="var(--via-danger)" delay={1.6} reduce={reduce} />
                  <Marker cx={66} cy={96} color="var(--via-muted)" delay={2.6} reduce={reduce} />
                </svg>

                <AnimatePresence>
                  <Callout key="a" x={184} y={40} title="Copper spacing below 0.150 mm" detail="GND / SIG · smallest gap 0.118 mm" delay={1.3} severity="high" />
                  <Callout key="b" x={78} y={150} title="Pad without net" detail="R1 pad 2 · F.Cu · no net assigned" delay={1.7} severity="low" />
                </AnimatePresence>
              </div>
            </div>
          </div>

          <figcaption className="flex items-center justify-between gap-3 border-t border-border px-4 py-2 font-mono text-[10.5px] text-subtle">
            <span>Illustration · toggle the layers</span>
            <span className="hidden sm:inline">2 findings · 1 high · 1 low</span>
          </figcaption>
        </Glass>
      </m.div>
    </div>
  );
}
