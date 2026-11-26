"use client";

import type { Design, Project } from "@via/types";
import { Badge, Card, CardHeader, CardTitle, EmptyState, ErrorState, Skeleton } from "@via/ui";
import { BarChart3 } from "lucide-react";
import Link from "next/link";

import { useApi } from "@/components/api-context";
import { errorMessage } from "@/lib/errors";
import { SEVERITIES, severityTone } from "@/lib/findings";
import { formatDateTime } from "@/lib/format";
import { useAsync } from "@/lib/use-async";

/** Project-level analysis overview: each design's latest analysis, linking to its Analysis tab. */
export function ProjectAnalysisSection({ project }: { project: Project }) {
  const client = useApi();
  const designs = useAsync((s) => client.designs.list(project.id, s), [client, project.id]);
  if (designs.error) return <ErrorState title="Couldn't load designs" description={errorMessage(designs.error)} />;
  if (!designs.data) return <Skeleton className="h-40 w-full" />;
  return (
    <Card>
      <CardHeader>
        <div>
          <CardTitle>Analysis</CardTitle>
          <p className="text-xs text-muted">
            The latest analysis of each design. Open a design&apos;s Analysis tab to run checks, inspect findings on the board and review them.
          </p>
        </div>
      </CardHeader>
      {designs.data.length === 0 ? (
        <EmptyState icon={<BarChart3 />} title="No designs yet" description="Upload a KiCad board on the PCB Designs tab, then analyse it." />
      ) : (
        <ul aria-label="Design analyses" className="divide-y divide-border">
          {designs.data.map((d) => <DesignRow key={d.id} project={project} design={d} />)}
        </ul>
      )}
    </Card>
  );
}

function DesignRow({ project, design }: { project: Project; design: Design }) {
  const client = useApi();
  const runs = useAsync((s) => client.analysis.runs(design.id, { limit: 1 }, s), [client, design.id]);
  const run = runs.data?.items[0];
  const by = run?.summary.by_severity;
  const current = design.current_revision?.id;
  return (
    <li className="flex flex-wrap items-center gap-2 px-4 py-2 text-sm">
      <Link href={`/projects/${project.id}/designs/${design.id}?tab=analysis`} className="min-w-40 flex-1 font-medium text-accent hover:underline">
        {design.name}
      </Link>
      {runs.error ? <span className="text-xs text-danger">{errorMessage(runs.error)}</span> : !runs.data ? (
        <Skeleton className="h-4 w-40" />
      ) : !run ? (
        <span className="text-xs text-muted">Not analysed yet</span>
      ) : run.status === "succeeded" ? (
        <>
          <span>{run.summary.finding_count ?? 0} findings</span>
          {SEVERITIES.map((s) => (by?.[s] ? <Badge key={s} tone={severityTone(s)}>{by[s]} {s}</Badge> : null))}
          <span className="text-xs text-muted">
            rev {run.revision_number}{run.revision_id !== current ? " (not the current revision)" : ""}
            {run.finished_at ? ` · ${formatDateTime(run.finished_at)}` : ""}
          </span>
        </>
      ) : (
        <Badge tone={run.status === "failed" ? "danger" : "accent"}>{run.status}</Badge>
      )}
    </li>
  );
}
