"use client";

import { Button, cn, enter, enterReduced, Glass, SPRING_SOFT, stagger } from "@via/ui";
import {
  ArrowRight,
  ChevronRight,
  CircuitBoard,
  FileArchive,
  GitCompareArrows,
  Home,
  Layers,
  Lock,
  ScanSearch,
  Upload,
  Workflow,
} from "lucide-react";
import { m, useReducedMotion, useScroll, useTransform } from "motion/react";
import Link from "next/link";
import { Fragment, type ReactNode, useRef } from "react";

import { GlassCta } from "@/components/glass-cta";
import { LiquidGridBackground } from "@/components/liquid-grid-background";
import { SystemStatus } from "@/components/system-status";
import { ViaLogo } from "@/components/via-logo";

import { BentoCard, BentoGrid } from "./bento-grid";
import { ChecksCard } from "./checks-card";
import { ChecksVisual, ImportVisual, PrivacyVisual, RevisionsVisual, ViewerVisual } from "./feature-visuals";
import { HeroCarousel } from "./hero-carousel";
import { HowItWorks } from "./how-it-works";
import { SampleFinding } from "./sample-finding";

/** Headline words rise in one after another, blurring into focus. */
function Words({ text, className }: { text: string; className?: string }) {
  const reduce = useReducedMotion();
  return (
    <>
      {text.split(" ").map((w, i, all) => (
        <Fragment key={`${w}-${i}`}>
          <m.span
            className={cn("inline-block", className)}
            variants={reduce ? enterReduced : { hidden: { opacity: 0, y: "0.45em", filter: "blur(10px)" }, show: { opacity: 1, y: 0, filter: "blur(0px)", transition: SPRING_SOFT } }}
          >
            {w}
          </m.span>
          {i < all.length - 1 ? " " : null}
        </Fragment>
      ))}
    </>
  );
}

/** Hero copy: blur-fades in on load, staggered. */
function Rise({ children, className }: { children: ReactNode; className?: string }) {
  const reduce = useReducedMotion();
  return (
    <m.div variants={reduce ? enterReduced : enter} className={className}>
      {children}
    </m.div>
  );
}

/** Blur-fade a block in the first time it scrolls into view. */
function Reveal({ children, className, as = "div" }: { children: ReactNode; className?: string; as?: "div" | "section" }) {
  const reduce = useReducedMotion();
  const Comp = as === "section" ? m.section : m.div;
  return (
    <Comp initial="hidden" whileInView="show" viewport={{ once: true, amount: 0.2 }} variants={stagger(0.08)} className={className}>
      <m.div variants={reduce ? enterReduced : enter}>{children}</m.div>
    </Comp>
  );
}

function SectionHeading({ eyebrow, title, body, id }: { eyebrow: string; title: ReactNode; body?: ReactNode; id: string }) {
  return (
    <Reveal className="mb-12 max-w-2xl">
      <p className="font-mono text-[11.5px] uppercase tracking-[0.14em] text-accent">{eyebrow}</p>
      <h2 id={id} className="mt-3 font-display text-[2.1rem] font-bold leading-[1.05] tracking-[-0.02em] text-foreground sm:text-[2.9rem]">
        {title}
      </h2>
      {body ? <p className="mt-4 text-[16px] leading-relaxed text-muted">{body}</p> : null}
    </Reveal>
  );
}

const ACCENT = "not-italic text-accent";

// --------------------------------------------------------------------------- page

export function LandingPage() {
  const reduce = useReducedMotion();
  const hero = useRef<HTMLElement>(null);
  const { scrollYProgress } = useScroll({ target: hero, offset: ["start start", "end start"] });
  const boardY = useTransform(scrollYProgress, [0, 1], [0, reduce ? 0 : 60]);
  const copyY = useTransform(scrollYProgress, [0, 1], [0, reduce ? 0 : 30]);

  return (
    <div className="landing relative isolate overflow-x-clip">
      {/* Hero: editorial layout on the Liquid Grid. */}
      <section ref={hero} aria-labelledby="hero-title" className="relative isolate">
        <LiquidGridBackground className="-top-[84px] -z-10 [mask-image:radial-gradient(ellipse_75%_70%_at_40%_35%,#000_35%,transparent_80%)]" cellSize={24} />
        <div className="mx-auto grid max-w-[1360px] grid-cols-[minmax(0,1fr)] items-start gap-6 px-4 pb-24 pt-8 sm:px-6 lg:grid-cols-[minmax(0,1fr)_minmax(0,1.05fr)] lg:pt-14 xl:grid-cols-[minmax(0,1.22fr)_minmax(0,1fr)_minmax(0,0.8fr)]">
          <m.div style={{ y: copyY }} initial="hidden" animate="show" variants={stagger(0.07, 0.05)} className="lg:pr-6 lg:pt-10">
            <Rise>
              <nav aria-label="Breadcrumb">
                <ol className="glass-thin inline-flex items-center gap-2 rounded-full px-3 py-1.5 text-[13px] text-muted">
                  <li>
                    <Home className="size-3.5" aria-hidden="true" />
                    <span className="sr-only">VIA</span>
                  </li>
                  <li aria-hidden="true">
                    <ChevronRight className="size-3.5 text-subtle" />
                  </li>
                  <li aria-current="page" className="font-medium text-foreground">
                    KiCad design review
                  </li>
                </ol>
              </nav>
            </Rise>
            <h1 id="hero-title" className="mt-7 font-display text-[2.55rem] font-bold leading-[1.04] tracking-[-0.02em] text-foreground sm:text-[3.5rem] lg:text-[3.1rem] xl:text-[3.45rem]">
              <Words text="Deterministic design review for" />{" "}
              <Words text="KiCad" className="text-accent" /> <Words text="PCBs." />
            </h1>
            <Rise>
              <p className="mt-6 max-w-xl text-[17px] leading-[1.65] text-muted">
                VIA turns PCB design files into structured engineering data you can explore, review and build on. Every finding points to{" "}
                <span className="text-foreground">the exact objects and the measured value</span> behind it.
              </p>
            </Rise>
            <Rise className="mt-8 flex flex-wrap items-center gap-3">
              <GlassCta size="lg" label="Create account" link="/register" />
              <Button asChild variant="solid" size="lg">
                <Link href="/login">Sign in</Link>
              </Button>
            </Rise>
            <Rise>
              <ul aria-label="Supported inputs" className="mt-8 flex flex-wrap gap-2 font-mono text-[12px] text-muted">
                {[".kicad_pcb", "zipped KiCad projects", "KiCad 5–9"].map((c) => (
                  <li key={c} className="rounded-full border border-border-strong px-3.5 py-1.5">
                    {c}
                  </li>
                ))}
              </ul>
            </Rise>
          </m.div>
          <m.div
            style={{ y: boardY }}
            initial={reduce ? { opacity: 0 } : { opacity: 0, y: 40, scale: 0.97, filter: "blur(10px)" }}
            animate={{ opacity: 1, y: 0, scale: 1, filter: "blur(0px)" }}
            transition={{ type: "spring", stiffness: 120, damping: 22, delay: 0.15 }}
          >
            <HeroCarousel />
          </m.div>
          <m.div
            initial={reduce ? { opacity: 0 } : { opacity: 0, y: 40, filter: "blur(10px)" }}
            animate={{ opacity: 1, y: 0, filter: "blur(0px)" }}
            transition={{ type: "spring", stiffness: 120, damping: 22, delay: 0.3 }}
            className="lg:col-span-2 xl:col-span-1"
          >
            <ChecksCard />
          </m.div>
        </div>
      </section>

      {/* What VIA does */}
      <section aria-labelledby="features" className="mx-auto max-w-6xl px-4 py-24 sm:px-6">
        <SectionHeading
          id="features"
          eyebrow="What VIA does"
          title={
            <>
              From board file to <em className={ACCENT}>verified</em> findings.
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
      <section aria-labelledby="sample" className="mx-auto grid max-w-6xl grid-cols-[minmax(0,1fr)] items-center gap-10 px-4 py-24 sm:px-6 lg:grid-cols-[minmax(0,0.8fr)_minmax(0,1.2fr)]">
        <SectionHeading
          id="sample"
          eyebrow="Anatomy of a finding"
          title={
            <>
              Evidence, not <em className={ACCENT}>opinions</em>.
            </>
          }
          body="A finding records which check produced it, how it was verified, the objects involved, and the measured value next to the rule it breaks."
        />
        <Reveal>
          <SampleFinding />
        </Reveal>
      </section>

      {/* Status */}
      <Reveal as="section" className="mx-auto max-w-6xl px-4 pb-24 sm:px-6">
        <Glass variant="regular" className="flex flex-wrap items-center gap-x-5 gap-y-3 rounded-full px-6 py-3.5" aria-labelledby="status-heading">
          <h2 id="status-heading" className="text-[13px] font-semibold tracking-tight text-muted">
            Service status
          </h2>
          <SystemStatus compact pollMs={30000} />
          <Link href="/status" className="ml-auto inline-flex items-center gap-1 rounded-full text-[13px] text-muted transition-colors hover:text-foreground">
            View details <ArrowRight className="size-3.5" aria-hidden="true" />
          </Link>
        </Glass>
      </Reveal>

      {/* Final CTA */}
      <Reveal as="section" className="mx-auto max-w-6xl px-4 pb-24 sm:px-6">
        <Glass variant="regular" className="overflow-hidden rounded-[32px] px-6 py-16 text-center sm:px-12" aria-labelledby="cta">
          <LiquidGridBackground className="-z-10 [mask-image:radial-gradient(ellipse_70%_80%_at_50%_100%,#000_20%,transparent_75%)]" cellSize={22} opacity={0.8} />
          <div aria-hidden="true" className="pointer-events-none absolute inset-x-0 -bottom-1/2 -z-10 mx-auto h-full w-2/3 rounded-full bg-[radial-gradient(closest-side,var(--via-accent-glow),transparent)] opacity-50" />
          <h2 id="cta" className="mx-auto max-w-3xl font-display text-[2.2rem] font-bold leading-[1.05] tracking-[-0.02em] text-foreground sm:text-[3rem]">
            Review your next board with <em className={ACCENT}>evidence</em>.
          </h2>
          <p className="mx-auto mt-4 max-w-lg text-[16px] leading-relaxed text-muted">Create a private project, upload a KiCad board and run the checks.</p>
          <div className="mt-8 flex flex-wrap justify-center gap-3">
            <GlassCta size="lg" label="Create account" link="/register" />
            <Button asChild variant="solid" size="lg">
              <Link href="/login">Sign in</Link>
            </Button>
          </div>
        </Glass>
      </Reveal>

      <footer className="border-t border-border">
        <div className="mx-auto flex max-w-6xl flex-wrap items-center gap-x-6 gap-y-3 px-4 py-8 text-[13px] text-subtle sm:px-6">
          <ViaLogo />
          <span>Engineering intelligence for PCB design.</span>
          <nav aria-label="Footer" className="ml-auto flex gap-4">
            <Link href="/status" className="rounded-full hover:text-foreground">
              System status
            </Link>
            <Link href="/login" className="rounded-full hover:text-foreground">
              Sign in
            </Link>
            <Link href="/register" className="rounded-full hover:text-foreground">
              Create account
            </Link>
          </nav>
        </div>
      </footer>
    </div>
  );
}
