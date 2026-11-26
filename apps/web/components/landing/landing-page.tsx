"use client";

import { Button } from "@via/ui";
import {
  ArrowRight,
  CircuitBoard,
  FileArchive,
  GitCompareArrows,
  Layers,
  Lock,
  ScanSearch,
  Upload,
  Workflow,
} from "lucide-react";
import { domAnimation, LazyMotion, m, MotionConfig, useReducedMotion } from "motion/react";
import Link from "next/link";
import type { ReactNode } from "react";

import { SystemStatus } from "@/components/system-status";
import { ViaLogo } from "@/components/via-logo";

import { BentoCard, BentoGrid } from "./bento-grid";
import { BoardMockup } from "./board-mockup";
import { HowItWorks } from "./how-it-works";
import { SampleFinding } from "./sample-finding";

const EASE = [0.22, 1, 0.36, 1] as const;

function Rise({ children, delay = 0, className }: { children: ReactNode; delay?: number; className?: string }) {
  const reduce = useReducedMotion();
  return (
    <m.div initial={{ opacity: 0, y: reduce ? 0 : 12 }} animate={{ opacity: 1, y: 0 }} transition={{ delay, duration: 0.6, ease: EASE }} className={className}>
      {children}
    </m.div>
  );
}

function SectionHeading({ eyebrow, title, body, id }: { eyebrow: string; title: ReactNode; body?: ReactNode; id: string }) {
  return (
    <div className="mb-10 max-w-2xl">
      <p className="font-mono text-[11px] uppercase tracking-[0.14em] text-accent">{eyebrow}</p>
      <h2 id={id} className="font-display mt-3 text-[2rem] leading-[1.1] text-foreground sm:text-[2.6rem]">
        {title}
      </h2>
      {body ? <p className="mt-3 text-[15px] leading-relaxed text-muted">{body}</p> : null}
    </div>
  );
}

// ------------------------------------------------------------------- feature visuals

function ImportVisual() {
  return (
    <div className="flex w-full max-w-xs items-center gap-3 font-mono text-[11px]">
      <div className="flex flex-col gap-1.5">
        {[".kicad_pcb", ".zip", ".kicad_pro"].map((f) => (
          <span key={f} className="rounded-md border border-border bg-surface-raised px-2 py-1 text-muted">
            {f}
          </span>
        ))}
      </div>
      <svg viewBox="0 0 60 60" className="h-14 w-10 shrink-0 text-accent" fill="none">
        <path d="M2 10 C 30 10, 30 30, 58 30 M2 30 H58 M2 50 C 30 50, 30 30, 58 30" stroke="currentColor" strokeWidth="1.2" strokeOpacity="0.7" />
      </svg>
      <div className="flex-1 rounded-md border border-accent-border bg-accent-soft px-2.5 py-2 text-[10.5px] leading-relaxed text-muted">
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

function ViewerVisual() {
  return (
    <svg viewBox="0 0 220 120" className="h-28 w-full max-w-[16rem]">
      <rect x="10" y="8" width="200" height="104" rx="8" fill="var(--landing-board)" stroke="var(--via-warning)" strokeOpacity="0.7" />
      <g stroke="var(--via-accent)" strokeOpacity="0.55" strokeWidth="4" fill="none" strokeLinecap="round">
        <path d="M40 30 V20 H160 L176 36 V60" />
      </g>
      <g stroke="var(--landing-copper)" strokeWidth="3.5" fill="none" strokeLinecap="round" strokeLinejoin="round">
        <path d="M30 50 H90 L104 64 H130" />
        <path d="M30 72 H80 L96 88 H130" />
        <path d="M156 70 H190" />
      </g>
      <rect x="128" y="52" width="28" height="44" rx="3" fill="none" stroke="var(--via-foreground)" strokeOpacity="0.5" />
      <rect x="126" y="58" width="32" height="32" rx="4" fill="none" stroke="var(--via-accent)" strokeWidth="1.5" strokeDasharray="3 3" />
      <text x="128" y="108" fontSize="8" fontFamily="var(--font-mono)" fill="var(--via-muted)">U1 · QFN-24</text>
    </svg>
  );
}

function ChecksVisual() {
  const rows: [string, string, string][] = [
    ["connectivity", "ok", "text-success"],
    ["manufacturing", "2", "text-danger"],
    ["placement", "ok", "text-success"],
    ["routing", "1", "text-warning"],
    ["kicad_drc", "15", "text-danger"],
  ];
  return (
    <div className="w-full max-w-sm space-y-1.5 font-mono text-[11px]">
      {rows.map(([name, n, tone]) => (
        <div key={name} className="flex items-center gap-2 rounded-md border border-border bg-surface-raised px-2.5 py-1.5">
          <span className="size-1.5 rounded-full bg-accent/70" />
          <span className="text-muted">{name}</span>
          <span className="mx-1 h-px flex-1 bg-border" />
          <span className={tone}>{n}</span>
        </div>
      ))}
    </div>
  );
}

function RevisionsVisual() {
  return (
    <div className="flex w-full max-w-xs flex-col gap-2 font-mono text-[11px]">
      {[
        ["r1", "imported", "text-subtle"],
        ["r2", "change set applied · re-checked", "text-foreground"],
        ["r3", "rolled back to r1", "text-subtle"],
      ].map(([r, label, tone], i) => (
        <div key={r} className="flex items-center gap-2.5">
          <span className={`flex size-6 items-center justify-center rounded-full border ${i === 1 ? "border-accent bg-accent-soft text-accent" : "border-border-strong text-subtle"}`}>{r}</span>
          <span className={tone}>{label}</span>
        </div>
      ))}
    </div>
  );
}

function PrivacyVisual() {
  return (
    <div className="flex items-center gap-3 font-mono text-[11px] text-muted">
      <span className="flex size-12 items-center justify-center rounded-lg border border-border-strong bg-surface-raised text-accent">
        <Lock className="size-5" aria-hidden="true" />
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

// --------------------------------------------------------------------------- page

export function LandingPage() {
  return (
    <MotionConfig reducedMotion="user">
      <LazyMotion features={domAnimation} strict>
        <div className="landing relative isolate overflow-x-clip">
          {/* Background: grid, glow, grain. Decorative. */}
          <div aria-hidden="true" className="pointer-events-none absolute inset-x-0 top-0 -z-10 h-[1100px]">
            <div className="landing-glow absolute inset-0" />
            <div className="landing-grid absolute inset-0" />
          </div>
          <div aria-hidden="true" className="landing-grain pointer-events-none fixed inset-0 -z-10" />

          {/* Hero */}
          <section aria-labelledby="hero-title" className="mx-auto grid max-w-6xl items-center gap-12 px-4 pb-20 pt-14 sm:px-6 lg:grid-cols-[minmax(0,0.9fr)_minmax(0,1.1fr)] lg:pt-20">
            <div>
              <Rise>
                <p className="inline-flex items-center gap-2 rounded-full border border-border bg-surface/70 px-3 py-1 font-mono text-[11px] text-muted backdrop-blur">
                  <span className="size-1.5 rounded-full bg-accent shadow-[0_0_8px_var(--landing-glow)]" aria-hidden="true" />
                  Engineering intelligence for PCB design
                </p>
              </Rise>
              <Rise delay={0.08}>
                <h1 id="hero-title" className="font-display mt-6 text-[2.6rem] leading-[1.02] text-foreground sm:text-[3.4rem] lg:text-[3.5rem] xl:text-[3.85rem]">
                  Deterministic design review for <em className="text-accent-hover">KiCad</em> PCBs.
                </h1>
              </Rise>
              <Rise delay={0.16}>
                <p className="mt-6 max-w-xl text-[16px] leading-relaxed text-muted">
                  VIA turns PCB design files into structured engineering data you can explore, review and build on. Every finding points to the exact objects
                  and the measured value behind it.
                </p>
              </Rise>
              <Rise delay={0.24} className="mt-8 flex flex-wrap items-center gap-3">
                <Button asChild variant="primary" size="lg" className="group shadow-[0_8px_30px_-8px_var(--landing-glow)]">
                  <Link href="/register">
                    Create account <ArrowRight className="transition-transform duration-200 group-hover:translate-x-0.5" />
                  </Link>
                </Button>
                <Button asChild variant="secondary" size="lg">
                  <Link href="/login">Sign in</Link>
                </Button>
              </Rise>
              <Rise delay={0.32}>
                <p className="mt-8 font-mono text-[11.5px] text-subtle">
                  .kicad_pcb <span className="text-border-strong">·</span> zipped KiCad projects <span className="text-border-strong">·</span> KiCad 5–9
                </p>
              </Rise>
            </div>
            <Rise delay={0.2}>
              <BoardMockup />
            </Rise>
          </section>

          {/* What VIA does */}
          <section aria-labelledby="features" className="mx-auto max-w-6xl px-4 py-20 sm:px-6">
            <SectionHeading
              id="features"
              eyebrow="What VIA does"
              title={
                <>
                  From board file to <em className="text-accent-hover">verified</em> findings.
                </>
              }
              body="Every step works on the real parsed board, not on screenshots or guesses."
            />
            <BentoGrid>
              <BentoCard
                colSpan={2}
                icon={<FileArchive />}
                title="KiCad ingestion"
                description="Import a .kicad_pcb or a zipped KiCad project. Boards are parsed into a tool-independent model: outline, layers, nets, footprints, pads, tracks, vias and zones."
                visual={<ImportVisual />}
                meta=".kicad_pcb · .zip with .kicad_pro / .kicad_dru rules"
              />
              <BentoCard
                rowSpan={2}
                icon={<ScanSearch />}
                title="Deterministic checks + KiCad DRC"
                description="Connectivity, manufacturing, placement and routing checks, plus KiCad's own DRC. Each finding names the exact objects and the measured value against the rule."
                visual={<ChecksVisual />}
                meta="source · verification · evidence on every finding"
              />
              <BentoCard
                icon={<Layers />}
                title="Board viewer"
                description="Inspect the real parsed board: toggle layers, select components and read their properties."
                visual={<ViewerVisual />}
              />
              <BentoCard
                icon={<GitCompareArrows />}
                title="Validated revisions"
                description="Proposed changes are validated by re-running the checks, then saved as revisions you can compare, download or roll back."
                visual={<RevisionsVisual />}
              />
              <BentoCard
                colSpan={3}
                icon={<Lock />}
                title="Private by default"
                description="Designs live in projects that are private by default, with access enforced on the server. Uploaded files are never executed."
                visual={<PrivacyVisual />}
                horizontal
              />
            </BentoGrid>
          </section>

          {/* How it works */}
          <section aria-labelledby="how" className="mx-auto max-w-6xl px-4 py-20 sm:px-6">
            <SectionHeading id="how" eyebrow="How it works" title="Upload. Parse. Analyze. Revise." />
            <HowItWorks
              steps={[
                { icon: <Upload />, title: "Upload", body: "Drop a board file or a zipped KiCad project into a private project.", detail: ".kicad_pcb · .zip" },
                { icon: <Workflow />, title: "Parse", body: "VIA builds a tool-independent model of the board and shows it in the viewer.", detail: "layers · nets · footprints · pads" },
                { icon: <ScanSearch />, title: "Analyze", body: "Deterministic checks and KiCad DRC run on the parsed board.", detail: "findings → objects + measured values" },
                { icon: <CircuitBoard />, title: "Revise", body: "Validate a change by re-running the checks, then keep it as a new revision.", detail: "compare · download · roll back" },
              ]}
            />
          </section>

          {/* Sample finding */}
          <section aria-labelledby="sample" className="mx-auto grid max-w-6xl items-center gap-10 px-4 py-20 sm:px-6 lg:grid-cols-[minmax(0,0.8fr)_minmax(0,1.2fr)]">
            <SectionHeading
              id="sample"
              eyebrow="Anatomy of a finding"
              title={
                <>
                  Evidence, not <em className="text-accent-hover">opinions</em>.
                </>
              }
              body="A finding records which check produced it, how it was verified, the objects involved, and the measured value next to the rule it breaks."
            />
            <SampleFinding />
          </section>

          {/* Status */}
          <section aria-labelledby="status-heading" className="mx-auto max-w-6xl px-4 pb-20 sm:px-6">
            <div className="flex flex-wrap items-center gap-x-5 gap-y-3 rounded-xl border border-border bg-surface/70 px-5 py-3.5 backdrop-blur">
              <h2 id="status-heading" className="font-mono text-[11px] uppercase tracking-[0.14em] text-subtle">
                Service status
              </h2>
              <SystemStatus compact pollMs={30000} />
              <Link href="/status" className="ml-auto inline-flex items-center gap-1 text-[13px] text-muted transition-colors hover:text-foreground">
                View details <ArrowRight className="size-3.5" aria-hidden="true" />
              </Link>
            </div>
          </section>

          {/* Final CTA */}
          <section aria-labelledby="cta" className="mx-auto max-w-6xl px-4 pb-24 sm:px-6">
            <div className="relative overflow-hidden rounded-2xl border border-border bg-surface px-6 py-14 text-center sm:px-12">
              <div aria-hidden="true" className="landing-glow pointer-events-none absolute inset-0 opacity-80" />
              <div aria-hidden="true" className="landing-grid pointer-events-none absolute inset-0 [mask-image:radial-gradient(ellipse_70%_80%_at_50%_100%,#000,transparent)]" />
              <div className="relative">
                <h2 id="cta" className="font-display mx-auto max-w-2xl text-[2.2rem] leading-[1.08] text-foreground sm:text-[3rem]">
                  Review your next board with <em className="text-accent-hover">evidence</em>.
                </h2>
                <p className="mx-auto mt-4 max-w-lg text-[15px] text-muted">Create a private project, upload a KiCad board and run the checks.</p>
                <div className="mt-8 flex flex-wrap justify-center gap-3">
                  <Button asChild variant="primary" size="lg" className="group shadow-[0_8px_30px_-8px_var(--landing-glow)]">
                    <Link href="/register">
                      Create account <ArrowRight className="transition-transform duration-200 group-hover:translate-x-0.5" />
                    </Link>
                  </Button>
                  <Button asChild variant="secondary" size="lg">
                    <Link href="/login">Sign in</Link>
                  </Button>
                </div>
              </div>
            </div>
          </section>

          <footer className="border-t border-border">
            <div className="mx-auto flex max-w-6xl flex-wrap items-center gap-x-6 gap-y-3 px-4 py-6 text-[13px] text-subtle sm:px-6">
              <ViaLogo />
              <span>Engineering intelligence for PCB design.</span>
              <nav aria-label="Footer" className="ml-auto flex gap-4">
                <Link href="/status" className="hover:text-foreground">
                  System status
                </Link>
                <Link href="/login" className="hover:text-foreground">
                  Sign in
                </Link>
                <Link href="/register" className="hover:text-foreground">
                  Create account
                </Link>
              </nav>
            </div>
          </footer>
        </div>
      </LazyMotion>
    </MotionConfig>
  );
}
