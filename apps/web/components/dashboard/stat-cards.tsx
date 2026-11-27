"use client";

import type { FindingListPage, ProjectSummary, RunListItem, Severity } from "@via/types";
import { cn, CountUp, enter, enterReduced, Skeleton, stagger } from "@via/ui";
import { m, useReducedMotion } from "motion/react";
import Link from "next/link";
import type { ReactNode } from "react";

import { SEVERITIES } from "@/lib/findings";
import { formatDateTime, relativeTime } from "@/lib/format";

// Severity counts are quiet text; only the severities that need attention carry their status colour.
const SEV_TEXT: Record<Severity, string> = {
  critical: "text-danger",
  high: "text-danger",
  medium: "text-warning",
  low: "text-muted",
  info: "text-muted",
};

function Card({ label, href, children, foot }: { label: string; href: string; children: ReactNode; foot: ReactNode }) {
  const reduce = useReducedMotion();
  return (
    <m.li variants={reduce ? enterReduced : enter} className="min-w-0">
      <Link href={href} className="glass-regular group flex h-full flex-col justify-between gap-4 rounded-3xl p-5 backdrop-blur-none transition-colors hover:bg-surface-hover">
        <p className="text-[13px] text-muted">{label}</p>
        <div className="min-w-0">{children}</div>
        <div className="font-mono text-[12px] text-subtle">{foot}</div>
      </Link>
    </m.li>
  );
}

const Big = ({ children, dim = false }: { children: ReactNode; dim?: boolean }) => (
  <p className={cn("font-display text-[40px] font-normal leading-none tracking-[-0.02em] tabular-nums", dim ? "text-subtle" : "text-foreground")}>{children}</p>
);

interface Props {
  summary: ProjectSummary | undefined;
  findings: FindingListPage | undefined;
  revisions: number | undefined;
  lastRun: RunListItem | null | undefined;
}

/**
 * Four headline numbers, all from real API fields: boards with a succeeded analysis, open findings
 * in each board's latest run (by severity), revisions across your designs, and the most recent
 * analysis. Empty data gets a plain zero state, never a placeholder number.
 */
export function StatCards({ summary, findings, revisions, lastRun }: Props) {
  const sev = SEVERITIES.map((s) => [s, findings?.by_severity?.[s] ?? 0] as [Severity, number]).filter(([, n]) => n > 0);
  return (
    <m.ul initial="hidden" animate="show" variants={stagger(0.06)} className="grid grid-cols-1 gap-4 sm:grid-cols-2 xl:grid-cols-4" aria-label="Overview">
      <Card label="Boards analysed" href="/analysis" foot={summary ? `of ${summary.designs} ${summary.designs === 1 ? "design" : "designs"}` : " "}>
        {findings ? <Big dim={!findings.designs_analysed}><CountUp value={findings.designs_analysed} /></Big> : <Skeleton className="h-11 w-16" />}
      </Card>

      <Card
        label="Open findings"
        href="/analysis"
        foot={
          findings ? (
            sev.length ? (
              <span className="flex flex-wrap gap-x-3 gap-y-1">
                {sev.map(([s, n]) => (
                  <span key={s} className={cn("tabular-nums", SEV_TEXT[s])}>
                    {n} {s}
                  </span>
                ))}
              </span>
            ) : findings.designs_analysed ? (
              "none open in the latest runs"
            ) : (
              "run an analysis to see findings"
            )
          ) : (
            " "
          )
        }
      >
        {findings ? <Big dim={!findings.total}><CountUp value={findings.total} /></Big> : <Skeleton className="h-11 w-16" />}
      </Card>

      <Card label="Revisions" href="/designs" foot={summary ? `+${summary.imports_7d} in the last 7 days` : " "}>
        {revisions === undefined ? <Skeleton className="h-11 w-16" /> : <Big dim={!revisions}><CountUp value={revisions} /></Big>}
      </Card>

      <Card
        label="Last analysis"
        href={lastRun ? `/projects/${lastRun.project.id}/designs/${lastRun.design.id}?tab=analysis` : "/analysis"}
        foot={lastRun ? <span className="block truncate">{lastRun.design.name} · r{lastRun.revision_number} · {lastRun.status}</span> : lastRun === null ? "no analyses yet" : " "}
      >
        {lastRun === undefined ? (
          <Skeleton className="h-11 w-28" />
        ) : lastRun ? (
          <p className="truncate font-display text-[32px] font-normal leading-[40px] tracking-[-0.02em] text-foreground" title={formatDateTime(lastRun.finished_at ?? lastRun.created_at)}>
            {relativeTime(lastRun.finished_at ?? lastRun.created_at)}
          </p>
        ) : (
          <Big dim>–</Big>
        )}
      </Card>
    </m.ul>
  );
}
