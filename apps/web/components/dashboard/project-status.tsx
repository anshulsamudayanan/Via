import type { LatestAnalysis, LatestImport, Severity } from "@via/types";
import { cn, CountUp, Mono, StatusDot, type StatusTone } from "@via/ui";
import Link from "next/link";

import { formatDateTime, relativeTime } from "@/lib/format";
import { SEVERITIES, severityTone } from "@/lib/findings";

const IMPORT: Record<LatestImport["status"], { label: string; tone: StatusTone }> = {
  pending: { label: "Queued", tone: "accent" },
  processing: { label: "Importing", tone: "accent" },
  ready: { label: "Imported", tone: "ok" },
  failed: { label: "Import failed", tone: "error" },
};

const CHIP: Record<ReturnType<typeof severityTone>, string> = {
  danger: "bg-danger-soft text-danger",
  warning: "bg-warning-soft text-warning",
  neutral: "bg-surface-hover text-muted",
};

/** The project's most recent upload: design, revision and import state, linking to that design. */
export function LastRevision({ projectId, value }: { projectId: string; value: LatestImport | null | undefined }) {
  if (!value) return <span className="text-xs text-subtle">No uploads</span>;
  const s = IMPORT[value.status];
  return (
    <Link
      href={`/projects/${projectId}/designs/${value.design_id}`}
      title={`${value.design_name}, revision ${value.revision_number}: ${s.label.toLowerCase()} ${formatDateTime(value.at)}`}
      className="group/rev inline-flex max-w-full items-center gap-1.5 rounded-sm text-xs text-muted hover:text-foreground"
    >
      <StatusDot tone={s.tone} />
      <span className="sr-only">{s.label}:</span>
      <span className="min-w-0 truncate">{value.design_name}</span>
      <Mono className="shrink-0 text-subtle group-hover/rev:text-muted">r{value.revision_number}</Mono>
    </Link>
  );
}

/** When the latest analysis ran, or what it is doing now. */
export function LastAnalyzed({ value }: { value: LatestAnalysis | null | undefined }) {
  if (!value) return <span className="text-xs text-subtle">Not analysed</span>;
  if (value.status === "queued" || value.status === "running") {
    return (
      <span className="inline-flex items-center gap-1.5 text-xs text-muted">
        <StatusDot tone="accent" /> {value.status === "queued" ? "Queued" : "Running"}
      </span>
    );
  }
  return (
    <time dateTime={value.at} title={formatDateTime(value.at)} className="whitespace-nowrap text-xs text-muted tabular-nums">
      {relativeTime(value.at)}
    </time>
  );
}

/** Findings of the latest succeeded analysis, split by severity; links to that design's Analysis tab. */
export function SeverityCounts({ projectId, value, className }: { projectId: string; value: LatestAnalysis | null | undefined; className?: string }) {
  if (!value) return <span className={cn("text-xs text-subtle", className)}>–</span>;
  const href = `/projects/${projectId}/designs/${value.design_id}?tab=analysis`;
  if (value.status === "failed") {
    return (
      <Link href={href} className={cn("inline-flex items-center gap-1.5 text-xs text-danger hover:underline", className)}>
        <StatusDot tone="error" /> Analysis failed
      </Link>
    );
  }
  if (value.status !== "succeeded") return <span className={cn("text-xs text-subtle", className)}>Pending</span>;

  const total = value.finding_count ?? 0;
  const counts = SEVERITIES.map((s) => [s, value.by_severity?.[s] ?? 0] as [Severity, number]).filter(([, n]) => n > 0);
  const label = total === 0 ? "No findings" : counts.length ? counts.map(([s, n]) => `${n} ${s}`).join(", ") : `${total} findings`;
  return (
    <Link
      href={href}
      aria-label={`${label}: open the analysis for ${value.design_name}`}
      title={`${value.design_name}: ${total} ${total === 1 ? "finding" : "findings"}`}
      className={cn("inline-flex max-w-full flex-wrap items-center gap-1 rounded-sm hover:opacity-80", className)}
    >
      {total === 0 ? (
        <span className="inline-flex items-center gap-1.5 text-xs text-muted">
          <StatusDot tone="ok" /> No findings
        </span>
      ) : counts.length ? (
        counts.map(([s, n]) => (
          <span key={s} className={cn("inline-flex items-center gap-1 rounded-full px-2 py-px text-[11px] font-medium leading-4", CHIP[severityTone(s)])}>
            <CountUp value={n} className="font-mono tabular-nums" />
            <span>{s}</span>
          </span>
        ))
      ) : (
        // Runs recorded before severity counts were stored: show the total only.
        <span className="text-xs text-muted">
          <Mono>{total}</Mono> {total === 1 ? "finding" : "findings"}
        </span>
      )}
    </Link>
  );
}
