"use client";

import { Button, enter, enterReduced, Glass, stagger } from "@via/ui";
import { ArrowRight, CircuitBoard, FileArchive, GitCompareArrows, Layers, Lock, ScanSearch, Upload, Workflow } from "lucide-react";
import { m, useReducedMotion } from "motion/react";
import Link from "next/link";
import type { ReactNode } from "react";

import { SystemStatus } from "@/components/system-status";
import { ViaLogo } from "@/components/via-logo";

import { BentoCard, BentoGrid } from "./bento-grid";
import { ChecksCard } from "./checks-card";
import { ImportVisual, PrivacyVisual, RevisionsVisual, ViewerVisual } from "./feature-visuals";
import { HeroCarousel } from "./hero-carousel";
import { HowItWorks } from "./how-it-works";
import { SampleFinding } from "./sample-finding";

function SectionHeading({ eyebrow, title, body, id }: { eyebrow: string; title: ReactNode; body?: ReactNode; id: string }) {
  return (
    <div className="mb-12 max-w-2xl">
      <p className="text-[14px] text-muted">{eyebrow}</p>
      <h2 id={id} className="mt-3 font-display text-[2rem] font-normal leading-[1.1] tracking-[-0.02em] text-foreground sm:text-[2.5rem]">
        {title}
      </h2>
      {body ? <p className="mt-4 text-[16px] leading-relaxed text-muted">{body}</p> : null}
    </div>
  );
}

// --------------------------------------------------------------------------- page

export function LandingPage() {
  const reduce = useReducedMotion();
  const rise = reduce ? enterReduced : enter;

  return (
    <div className="landing relative isolate overflow-x-clip">
      {/* Hero: what VIA does on the left, what it shows on the right. One entrance on load. */}
      <section aria-labelledby="hero-title" className="relative isolate">
        <m.div
          initial="hidden"
          animate="show"
          variants={stagger(0.06)}
          className="mx-auto grid max-w-6xl grid-cols-[minmax(0,1fr)] items-center gap-12 px-4 pb-24 pt-12 sm:px-6 lg:min-h-[calc(100svh-84px)] lg:grid-cols-[minmax(0,0.85fr)_minmax(0,1.15fr)] lg:gap-16 lg:pb-16 lg:pt-8"
        >
          <m.div variants={rise}>
            <p className="font-mono text-[12px] text-subtle">.kicad_pcb · zipped KiCad projects · KiCad 5–9</p>
            <h1 id="hero-title" className="mt-5 font-display text-[2.5rem] font-normal leading-[1.06] tracking-[-0.02em] text-foreground sm:text-[3.5rem]">
              Deterministic design review for KiCad PCBs
            </h1>
            <p className="mt-6 max-w-[36rem] text-[18px] leading-[1.6] text-muted">
              VIA turns PCB design files into structured engineering data you can explore, review and build on. Every finding points to the exact objects and the
              measured value behind it.
            </p>
            <div className="mt-8 flex flex-wrap items-center gap-3">
              <Button asChild variant="primary" size="lg">
                <Link href="/register">Create account</Link>
              </Button>
              <Button asChild variant="ghost" size="lg" className="text-foreground">
                <Link href="/login">Sign in</Link>
              </Button>
            </div>
          </m.div>
          <m.div variants={rise}>
            <HeroCarousel />
          </m.div>
        </m.div>
      </section>

      {/* What VIA does */}
      <section aria-labelledby="features" className="mx-auto max-w-6xl px-4 py-24 sm:px-6">
        <SectionHeading
          id="features"
          eyebrow="What VIA does"
          title="From board file to verified findings"
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
            visual={<ChecksCard />}
            visualHidden={false}
            meta="source · verification · evidence on every finding"
          />
          <BentoCard icon={<Layers />} title="Board viewer" description="Inspect the real parsed board: toggle layers, select components and read their properties." visual={<ViewerVisual />} />
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
      <section aria-labelledby="how" className="mx-auto max-w-6xl px-4 py-24 sm:px-6">
        <SectionHeading id="how" eyebrow="How it works" title="Upload, parse, analyze, revise" />
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
      <section aria-labelledby="sample" className="mx-auto grid max-w-6xl grid-cols-[minmax(0,1fr)] items-center gap-10 px-4 py-24 sm:px-6 lg:grid-cols-[minmax(0,0.8fr)_minmax(0,1.2fr)]">
        <SectionHeading
          id="sample"
          eyebrow="Anatomy of a finding"
          title="Evidence, not opinions"
          body="A finding records which check produced it, how it was verified, the objects involved, and the measured value next to the rule it breaks."
        />
        <SampleFinding />
      </section>

      {/* Status */}
      <section className="mx-auto max-w-6xl px-4 pb-24 sm:px-6" aria-labelledby="status-heading">
        <Glass variant="regular" className="flex flex-wrap items-center gap-x-5 gap-y-3 rounded-2xl px-5 py-3.5">
          <h2 id="status-heading" className="text-[13px] font-medium text-muted">
            Service status
          </h2>
          <SystemStatus compact pollMs={30000} />
          <Link href="/status" className="ml-auto inline-flex items-center gap-1 rounded-sm text-[13px] text-muted transition-colors hover:text-foreground">
            View details <ArrowRight className="size-3.5" aria-hidden="true" />
          </Link>
        </Glass>
      </section>

      {/* Final CTA */}
      <section className="mx-auto max-w-6xl px-4 pb-24 sm:px-6" aria-labelledby="cta">
        <Glass variant="regular" className="overflow-hidden rounded-4xl px-6 py-16 text-center sm:px-12">
          <h2 id="cta" className="mx-auto max-w-3xl font-display text-[2rem] font-normal leading-[1.1] tracking-[-0.02em] text-foreground sm:text-[2.5rem]">
            Review your next board with evidence
          </h2>
          <p className="mx-auto mt-4 max-w-lg text-[16px] leading-relaxed text-muted">Create a private project, upload a KiCad board and run the checks.</p>
          <div className="mt-8 flex flex-wrap justify-center gap-3">
            <Button asChild variant="primary" size="lg">
              <Link href="/register">Create account</Link>
            </Button>
            <Button asChild variant="ghost" size="lg" className="text-foreground">
              <Link href="/login">Sign in</Link>
            </Button>
          </div>
        </Glass>
      </section>

      <footer className="border-t border-border">
        <div className="mx-auto flex max-w-6xl flex-wrap items-center gap-x-6 gap-y-3 px-4 py-8 text-[13px] text-subtle sm:px-6">
          <ViaLogo />
          <span>Design review for KiCad boards</span>
          <nav aria-label="Footer" className="ml-auto flex gap-4">
            <Link href="/status" className="rounded-sm transition-colors hover:text-foreground">
              System status
            </Link>
            <Link href="/login" className="rounded-sm transition-colors hover:text-foreground">
              Sign in
            </Link>
            <Link href="/register" className="rounded-sm transition-colors hover:text-foreground">
              Create account
            </Link>
          </nav>
        </div>
      </footer>
    </div>
  );
}
