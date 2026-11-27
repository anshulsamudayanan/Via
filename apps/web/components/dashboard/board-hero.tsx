"use client";

import type { DesignListItem } from "@via/types";
import { LiquidGlass, Mono, Skeleton, useHoverCapable } from "@via/ui";
import { m, useMotionValue, useReducedMotion, useSpring, useTransform } from "motion/react";
import Link from "next/link";
import type { MouseEvent } from "react";

import { relativeTime } from "@/lib/format";

/**
 * A stylized two-layer board in 3D (SVG layers at different depths), tilting toward the cursor.
 * Decorative: it is not the user's board, and says so to assistive tech.
 */
function Board3D() {
  const reduce = useReducedMotion();
  const canHover = useHoverCapable();
  const px = useMotionValue(0);
  const py = useMotionValue(0);
  const sx = useSpring(px, { stiffness: 140, damping: 18 });
  const sy = useSpring(py, { stiffness: 140, damping: 18 });
  const rotateY = useTransform(sx, [-0.5, 0.5], [-28, -8]);
  const rotateX = useTransform(sy, [-0.5, 0.5], [62, 48]);
  const live = canHover && !reduce;

  function move(e: MouseEvent<HTMLDivElement>) {
    if (!live) return;
    const r = e.currentTarget.getBoundingClientRect();
    px.set((e.clientX - r.left) / r.width - 0.5);
    py.set((e.clientY - r.top) / r.height - 0.5);
  }

  const layer = "absolute inset-0 [backface-visibility:hidden]";
  return (
    <div
      aria-hidden="true"
      onMouseMove={move}
      onMouseLeave={() => {
        px.set(0);
        py.set(0);
      }}
      className="pointer-events-auto relative h-[210px] w-full [perspective:900px]"
    >
      <m.div
        style={{ rotateX: live ? rotateX : 55, rotateY: live ? rotateY : -18, rotateZ: 0, transformStyle: "preserve-3d" }}
        className="absolute left-1/2 top-[56%] h-[150px] w-[230px] -translate-x-1/2 -translate-y-1/2"
      >
        {/* Shadow on the card below */}
        <div className={`${layer} rounded-[14px] bg-black/50 blur-xl`} style={{ transform: "translateZ(-40px)" }} />
        {/* Substrate edge (thickness) */}
        <div className={`${layer} rounded-[12px] bg-[var(--via-mask-deep)]`} style={{ transform: "translateZ(-6px)" }} />
        {/* Board */}
        <svg viewBox="0 0 230 150" className={`${layer} overflow-visible`} style={{ transform: "translateZ(0px)" }}>
          <defs>
            <linearGradient id="b3d-fr4" x1="0" y1="0" x2="1" y2="1">
              <stop offset="0" stopColor="var(--via-mask)" />
              <stop offset="1" stopColor="var(--via-mask-deep)" />
            </linearGradient>
          </defs>
          <rect x="0.5" y="0.5" width="229" height="149" rx="12" fill="url(#b3d-fr4)" stroke="rgba(255,255,255,0.18)" />
          <g stroke="var(--via-copper)" strokeWidth="2.4" fill="none" strokeLinecap="round" strokeLinejoin="round" opacity="0.9">
            <path d="M24 40 H70 L82 52 H100" />
            <path d="M24 60 H64 L74 70 H100" />
            <path d="M150 56 H190 L204 42" />
            <path d="M150 80 H182 L196 94 V118" />
            <path d="M118 104 V124 H160" />
          </g>
          {/* Back-layer copper, seen through the mask */}
          <g stroke="var(--via-copper)" strokeWidth="2.4" fill="none" strokeLinecap="round" opacity="0.3">
            <path d="M40 24 H170 L186 36" />
            <path d="M30 112 H96 L108 124" />
          </g>
          {[
            [24, 40], [24, 60], [204, 42], [196, 118], [160, 124], [108, 124],
          ].map(([cx, cy]) => (
            <g key={`${cx}-${cy}`}>
              <circle cx={cx} cy={cy} r="4" fill="var(--via-pad)" />
              <circle cx={cx} cy={cy} r="1.6" fill="var(--via-mask-deep)" />
            </g>
          ))}
          {[[12, 12], [218, 12], [12, 138], [218, 138]].map(([cx, cy]) => (
            <circle key={`h${cx}-${cy}`} cx={cx} cy={cy} r="4" fill="#06050a" stroke="rgba(255,255,255,0.2)" />
          ))}
        </svg>
        {/* Components, raised above the copper */}
        <div className="absolute left-[100px] top-[44px] h-[52px] w-[50px] rounded-[4px] bg-[#0b0a10] shadow-[0_0_0_1px_rgba(255,255,255,0.12)]" style={{ transform: "translateZ(10px)" }}>
          <span className="absolute left-1.5 top-1.5 size-1.5 rounded-full bg-white/40" />
        </div>
        <div className="absolute left-[150px] top-[96px] h-[12px] w-[24px] rounded-[2px] bg-[var(--via-silk)]" style={{ transform: "translateZ(6px)" }} />
        <div className="absolute left-[40px] top-[84px] h-[12px] w-[24px] rounded-[2px] bg-[var(--via-silk)]" style={{ transform: "translateZ(6px)" }} />
        <div className="absolute left-[176px] top-[64px] h-[22px] w-[30px] rounded-[3px] bg-[#25252c] shadow-[0_0_0_1px_rgba(255,255,255,0.1)]" style={{ transform: "translateZ(8px)" }} />
      </m.div>
    </div>
  );
}

/** The hero card: your most recently updated board, with its real counts, and the 3D board floating out of the card. */
export function BoardHero({ latest }: { latest: DesignListItem | null | undefined }) {
  const counts = latest?.current_revision?.object_counts;
  const facts: [string, number | undefined][] = [
    ["components", counts?.component_count],
    ["nets", counts?.net_count],
    ["copper layers", counts?.copper_layer_count],
  ];
  return (
    <LiquidGlass variant="regular" as="section" aria-labelledby="board-hero-title" className="overflow-visible rounded-3xl p-5">
      <p className="text-[13px] text-muted">Latest board</p>
      <div className="-mx-5 -mt-16 mb-1">
        <Board3D />
      </div>
      {latest === undefined ? (
        <div className="space-y-2">
          <Skeleton className="h-6 w-40" />
          <Skeleton className="h-4 w-56" />
        </div>
      ) : latest ? (
        <>
          <h2 id="board-hero-title" className="truncate font-display text-[22px] font-normal tracking-[-0.02em] text-foreground">
            <Link href={`/projects/${latest.project.id}/designs/${latest.id}`} className="rounded-sm hover:underline">
              {latest.name}
            </Link>
          </h2>
          <p className="mt-0.5 truncate text-[13px] text-muted">
            {latest.project.name} · <Mono>r{latest.current_revision?.revision_number ?? "–"}</Mono> · updated {relativeTime(latest.updated_at)}
          </p>
          <dl className="mt-4 grid grid-cols-3 gap-2">
            {facts.map(([k, v]) => (
              <div key={k} className="flex flex-col-reverse gap-1 rounded-lg border border-border bg-surface px-3 py-2.5">
                <dt className="whitespace-nowrap text-[12px] text-muted">{k}</dt>
                <dd className="font-display text-[20px] leading-none tabular-nums text-foreground">{v ?? "–"}</dd>
              </div>
            ))}
          </dl>
        </>
      ) : (
        <>
          <h2 id="board-hero-title" className="font-display text-[22px] font-normal tracking-[-0.02em] text-foreground">
            No boards yet
          </h2>
          <p className="mt-0.5 text-[13px] text-muted">Upload a KiCad board to a project to see it here.</p>
        </>
      )}
    </LiquidGlass>
  );
}
