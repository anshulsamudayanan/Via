import type { LatestAnalysis, LatestImport } from "@via/types";
import { Mono, StatusDot, type StatusTone } from "@via/ui";
import Link from "next/link";

import { formatDateTime } from "@/lib/format";

const IMPORT: Record<LatestImport["status"], { label: string; tone: StatusTone }> = {
  pending: { label: "Queued", tone: "accent" },
  processing: { label: "Importing", tone: "accent" },
  ready: { label: "Imported", tone: "ok" },
  failed: { label: "Import failed", tone: "error" },
};

/** The project's most recent upload: status, revision, and a link to that design. */
export function LastImport({ projectId, value }: { projectId: string; value: LatestImport | null | undefined }) {
  if (!value) return <span className="text-xs text-subtle">No uploads</span>;
  const s = IMPORT[value.status];
  return (
    <Link
      href={`/projects/${projectId}/designs/${value.design_id}`}
      title={`${value.design_name}, revision ${value.revision_number}: ${formatDateTime(value.at)}`}
      className="inline-flex max-w-full items-center gap-1.5 text-xs text-muted hover:text-foreground"
    >
      <StatusDot tone={s.tone} />
      <span className="whitespace-nowrap">{s.label}</span>
      <Mono className="text-subtle">r{value.revision_number}</Mono>
    </Link>
  );
}

/** The project's most recent analysis run: findings when it succeeded, otherwise its state. */
export function LastAnalysis({ projectId, value }: { projectId: string; value: LatestAnalysis | null | undefined }) {
  if (!value) return <span className="text-xs text-subtle">Not analysed</span>;
  const href = `/projects/${projectId}/designs/${value.design_id}?tab=analysis`;
  const title = `${value.design_name}: ${formatDateTime(value.at)}`;
  const body =
    value.status === "succeeded" ? (
      <>
        <StatusDot tone={value.finding_count ? "warning" : "ok"} />
        <Mono>{value.finding_count ?? 0}</Mono>
        <span>{value.finding_count === 1 ? "finding" : "findings"}</span>
      </>
    ) : value.status === "failed" ? (
      <>
        <StatusDot tone="error" />
        <span>Failed</span>
      </>
    ) : (
      <>
        <StatusDot tone="accent" />
        <span>{value.status === "queued" ? "Queued" : "Running"}</span>
      </>
    );
  return (
    <Link href={href} title={title} className="inline-flex items-center gap-1.5 whitespace-nowrap text-xs text-muted hover:text-foreground">
      {body}
    </Link>
  );
}
