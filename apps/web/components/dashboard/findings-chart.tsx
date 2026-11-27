"use client";

/*
 * Findings reported by analyses, per day, over the last 30 days, split by severity. Real data only:
 * every succeeded run from GET /analysis/runs (newest 100) contributes its stored `by_severity`.
 *
 * Form (dataviz skill): change over time -> multi-line; severity is ordered -> a one-hue ramp
 * (--via-sev-1..4, validated as an ordinal ramp in both themes), 4 series, so a legend AND direct
 * end labels; crosshair + tooltip that also works from the keyboard; a table view.
 * Motion: lines draw in (pathLength), then a soft glow breathes; both off with reduced motion.
 */

import type { RunListItem } from "@via/types";
import { cn, LiquidGlass, SegmentedControl, Skeleton, SPRING_SOFT } from "@via/ui";
import { m, useReducedMotion } from "motion/react";
import { type KeyboardEvent, type PointerEvent, useId, useMemo, useRef, useState } from "react";

const DAYS = 30;
const SERIES = [
  { key: "critical", label: "Critical", color: "var(--via-sev-4)", pick: (b: Record<string, number>) => b.critical ?? 0 },
  { key: "high", label: "High", color: "var(--via-sev-3)", pick: (b: Record<string, number>) => b.high ?? 0 },
  { key: "medium", label: "Medium", color: "var(--via-sev-2)", pick: (b: Record<string, number>) => b.medium ?? 0 },
  { key: "low", label: "Low + info", color: "var(--via-sev-1)", pick: (b: Record<string, number>) => (b.low ?? 0) + (b.info ?? 0) },
] as const;

type Day = { date: Date; values: number[]; runs: number };

function dayKey(d: Date) {
  return `${d.getFullYear()}-${d.getMonth()}-${d.getDate()}`;
}

/** Buckets runs into the last DAYS local days (oldest first). */
export function bucketRuns(runs: RunListItem[], now: Date = new Date()): Day[] {
  const start = new Date(now.getFullYear(), now.getMonth(), now.getDate() - (DAYS - 1));
  const days: Day[] = Array.from({ length: DAYS }, (_, i) => ({ date: new Date(start.getFullYear(), start.getMonth(), start.getDate() + i), values: SERIES.map(() => 0), runs: 0 }));
  const index = new Map(days.map((d, i) => [dayKey(d.date), i]));
  for (const run of runs) {
    if (run.status !== "succeeded") continue;
    const i = index.get(dayKey(new Date(run.finished_at ?? run.created_at)));
    if (i === undefined) continue;
    const day = days[i]!;
    day.runs += 1;
    SERIES.forEach((s, k) => (day.values[k]! += s.pick(run.by_severity)));
  }
  return days;
}

const fmtDay = new Intl.DateTimeFormat(undefined, { month: "short", day: "numeric" });

function niceMax(v: number) {
  if (v <= 4) return 4;
  const pow = 10 ** Math.floor(Math.log10(v));
  const n = v / pow;
  return (n <= 2 ? 2 : n <= 5 ? 5 : 10) * pow;
}

const W = 640;
const H = 220;
const PAD = { l: 34, r: 76, t: 12, b: 26 };

export function FindingsChart({ runs }: { runs: RunListItem[] | undefined }) {
  const reduce = useReducedMotion();
  const id = useId();
  const [view, setView] = useState<"chart" | "table">("chart");
  const [hover, setHover] = useState<number | null>(null);
  const plotRef = useRef<SVGSVGElement>(null);

  const days = useMemo(() => (runs ? bucketRuns(runs) : []), [runs]);
  const max = niceMax(Math.max(0, ...days.flatMap((d) => d.values)));
  const total = days.reduce((a, d) => a + d.runs, 0);
  const x = (i: number) => PAD.l + (i / (DAYS - 1)) * (W - PAD.l - PAD.r);
  const y = (v: number) => H - PAD.b - (v / max) * (H - PAD.t - PAD.b);
  const paths = SERIES.map((_, k) => days.map((d, i) => `${i ? "L" : "M"}${x(i).toFixed(1)} ${y(d.values[k]!).toFixed(1)}`).join(" "));

  function onMove(e: PointerEvent<SVGSVGElement>) {
    const r = e.currentTarget.getBoundingClientRect();
    const px = ((e.clientX - r.left) / r.width) * W;
    setHover(Math.max(0, Math.min(DAYS - 1, Math.round(((px - PAD.l) / (W - PAD.l - PAD.r)) * (DAYS - 1)))));
  }
  function onKey(e: KeyboardEvent<SVGSVGElement>) {
    if (e.key !== "ArrowLeft" && e.key !== "ArrowRight") return;
    e.preventDefault();
    setHover((h) => Math.max(0, Math.min(DAYS - 1, (h ?? DAYS - 1) + (e.key === "ArrowRight" ? 1 : -1))));
  }

  const active = hover !== null ? days[hover] : undefined;
  return (
    <LiquidGlass variant="regular" as="section" aria-labelledby={`${id}-title`} className="flex min-w-0 flex-col rounded-3xl p-5 backdrop-blur-none">
      <div className="flex flex-wrap items-start gap-3">
        <div className="min-w-0 flex-1">
          <p className="font-mono text-[11px] uppercase tracking-[0.12em] text-subtle">Last {DAYS} days</p>
          <h2 id={`${id}-title`} className="mt-1 font-display text-[22px] font-semibold tracking-[-0.02em] text-foreground">
            Findings reported
          </h2>
          <p className="text-[12.5px] text-muted">Per day, from {total} succeeded {total === 1 ? "analysis" : "analyses"}; each run counts its own findings.</p>
        </div>
        <SegmentedControl
          aria-label="Findings view"
          value={view}
          onChange={setView}
          segments={[
            { value: "chart", label: "Chart" },
            { value: "table", label: "Table" },
          ]}
        />
      </div>

      {/* Legend: line keys mirror the marks. */}
      <ul className="mt-3 flex flex-wrap gap-x-4 gap-y-1 text-[12px] text-muted" aria-label="Severity">
        {SERIES.map((s) => (
          <li key={s.key} className="flex items-center gap-1.5">
            <span aria-hidden="true" className="h-0.5 w-3.5 rounded-full" style={{ background: s.color }} />
            {s.label}
          </li>
        ))}
      </ul>

      {!runs ? (
        <Skeleton className="mt-4 h-[220px] w-full rounded-2xl" />
      ) : total === 0 ? (
        <div className="mt-4 flex h-[220px] items-center justify-center rounded-2xl border border-dashed border-border-strong text-center text-[13px] text-muted">
          No analyses finished in the last {DAYS} days.
        </div>
      ) : view === "table" ? (
        <div className="mt-4 max-h-[260px] overflow-auto rounded-2xl border border-border">
          <table className="w-full text-[12.5px]">
            <caption className="sr-only">Findings reported per day by severity</caption>
            <thead className="sticky top-0 bg-surface-raised text-left text-muted">
              <tr>
                <th scope="col" className="px-3 py-2 font-medium">Day</th>
                {SERIES.map((s) => (
                  <th key={s.key} scope="col" className="px-3 py-2 text-right font-medium">{s.label}</th>
                ))}
                <th scope="col" className="px-3 py-2 text-right font-medium">Runs</th>
              </tr>
            </thead>
            <tbody>
              {days.filter((d) => d.runs).reverse().map((d) => (
                <tr key={dayKey(d.date)} className="border-t border-border">
                  <th scope="row" className="px-3 py-1.5 text-left font-normal text-foreground">{fmtDay.format(d.date)}</th>
                  {d.values.map((v, k) => (
                    <td key={SERIES[k]!.key} className="px-3 py-1.5 text-right font-mono tabular-nums text-foreground">{v}</td>
                  ))}
                  <td className="px-3 py-1.5 text-right font-mono tabular-nums text-muted">{d.runs}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      ) : (
        <div className="relative mt-3">
          <svg
            ref={plotRef}
            viewBox={`0 0 ${W} ${H}`}
            className="block h-auto w-full touch-none overflow-visible rounded-xl outline-none"
            role="img"
            aria-label={`Findings reported per day over the last ${DAYS} days. Use the left and right arrow keys to read each day, or switch to the table.`}
            tabIndex={0}
            onPointerMove={onMove}
            onPointerLeave={() => setHover(null)}
            onKeyDown={onKey}
            onBlur={() => setHover(null)}
          >
            <defs>
              <filter id={`${id}-glow`} x="-10%" y="-30%" width="120%" height="160%">
                <feGaussianBlur stdDeviation="4" />
              </filter>
            </defs>
            {/* Recessive grid and y axis */}
            {[0, 0.5, 1].map((t) => (
              <g key={t}>
                <line x1={PAD.l} x2={W - PAD.r} y1={y(max * t)} y2={y(max * t)} stroke="var(--via-border)" strokeDasharray={t ? "2 4" : undefined} />
                <text x={PAD.l - 8} y={y(max * t) + 3.5} textAnchor="end" fontSize="10" fontFamily="var(--font-mono)" fill="var(--via-subtle)">
                  {Math.round(max * t)}
                </text>
              </g>
            ))}
            {[0, Math.floor((DAYS - 1) / 2), DAYS - 1].map((i) => (
              <text key={i} x={x(i)} y={H - 6} textAnchor={i === 0 ? "start" : i === DAYS - 1 ? "end" : "middle"} fontSize="10" fontFamily="var(--font-mono)" fill="var(--via-subtle)">
                {fmtDay.format(days[i]!.date)}
              </text>
            ))}
            {/* Glow under each line, breathing gently */}
            {paths.map((d, k) => (
              <m.path
                key={`g${k}`}
                d={d}
                fill="none"
                stroke={SERIES[k]!.color}
                strokeWidth="5"
                filter={`url(#${id}-glow)`}
                initial={{ opacity: 0 }}
                animate={reduce ? { opacity: 0.35 } : { opacity: [0.25, 0.55, 0.25] }}
                transition={reduce ? { duration: 0 } : { duration: 4, repeat: Infinity, ease: "easeInOut", delay: 1.2 + k * 0.3 }}
              />
            ))}
            {/* The lines (2px) */}
            {paths.map((d, k) => (
              <m.path
                key={`l${k}`}
                d={d}
                fill="none"
                stroke={SERIES[k]!.color}
                strokeWidth="2"
                strokeLinejoin="round"
                strokeLinecap="round"
                initial={reduce ? false : { pathLength: 0 }}
                animate={{ pathLength: 1 }}
                transition={{ ...SPRING_SOFT, stiffness: 60, damping: 20, delay: k * 0.08 }}
              />
            ))}
            {/* Direct end labels (4 series) in text ink, keyed by a short line */}
            {SERIES.map((s, k) => {
              const last = days[DAYS - 1]!.values[k]!;
              // Spread labels so they never collide.
              const ys = SERIES.map((_, j) => y(days[DAYS - 1]!.values[j]!));
              const order = [...ys.keys()].sort((a, b) => ys[a]! - ys[b]!);
              const slot = order.indexOf(k);
              const ly = Math.min(H - PAD.b - 4, Math.max(PAD.t + 6, ys[order[0]!]! + slot * 13));
              return (
                <g key={s.key}>
                  <line x1={W - PAD.r + 6} x2={W - PAD.r + 14} y1={ly - 3.5} y2={ly - 3.5} stroke={s.color} strokeWidth="2" strokeLinecap="round" />
                  <text x={W - PAD.r + 18} y={ly} fontSize="10.5" fill="var(--via-muted)">
                    {s.label.split(" ")[0]} <tspan fontFamily="var(--font-mono)" fill="var(--via-foreground)">{last}</tspan>
                  </text>
                </g>
              );
            })}
            {/* Crosshair */}
            {hover !== null ? <line x1={x(hover)} x2={x(hover)} y1={PAD.t} y2={H - PAD.b} stroke="var(--via-border-strong)" /> : null}
            {hover !== null
              ? SERIES.map((s, k) => <circle key={s.key} cx={x(hover)} cy={y(days[hover]!.values[k]!)} r="4" fill={s.color} stroke="var(--via-background)" strokeWidth="2" />)
              : null}
          </svg>
          {active && hover !== null ? (
            <div
              role="status"
              className={cn("glass-overlay pointer-events-none absolute top-2 z-10 w-44 rounded-2xl px-3 py-2 text-[12px]", hover > DAYS / 2 ? "left-2" : "right-2")}
            >
              <p className="font-medium text-foreground">{fmtDay.format(active.date)}</p>
              <ul className="mt-1 space-y-0.5">
                {SERIES.map((s, k) => (
                  <li key={s.key} className="flex items-center gap-2">
                    <span aria-hidden="true" className="h-0.5 w-3 rounded-full" style={{ background: s.color }} />
                    <span className="font-mono font-medium tabular-nums text-foreground">{active.values[k]}</span>
                    <span className="text-muted">{s.label}</span>
                  </li>
                ))}
              </ul>
              <p className="mt-1 text-[11px] text-subtle">
                {active.runs} {active.runs === 1 ? "run" : "runs"}
              </p>
            </div>
          ) : null}
        </div>
      )}
    </LiquidGlass>
  );
}
