"use client";

import type { Design } from "@via/types";
import { Card, EmptyState, Table, TBody, TD, TH, THead, TR } from "@via/ui";
import { Layers } from "lucide-react";
import Link from "next/link";

import { RevisionStatusBadge } from "@/components/designs/revision-status";
import { formatDateTime, relativeTime } from "@/lib/format";

export function DesignsList({ projectId, designs }: { projectId: string; designs: Design[] }) {
  if (designs.length === 0) {
    return (
      <Card>
        <EmptyState icon={<Layers />} title="No designs yet" description="Upload a KiCad board to create the first design in this project." />
      </Card>
    );
  }
  return (
    <Card>
      <Table>
        <caption className="sr-only">PCB designs</caption>
        <THead>
          <tr>
            <TH>Design</TH>
            <TH>Status</TH>
            <TH className="hidden text-right md:table-cell">Components</TH>
            <TH className="hidden text-right md:table-cell">Nets</TH>
            <TH className="hidden text-right lg:table-cell">Layers</TH>
            <TH className="text-right">Updated</TH>
          </tr>
        </THead>
        <TBody>
          {designs.map((d) => {
            const latest = d.latest_revision;
            const counts = d.current_revision?.object_counts ?? {};
            return (
              <TR key={d.id} className="hover:bg-surface-hover">
                <TD className="max-w-0 w-2/5">
                  <Link href={`/projects/${projectId}/designs/${d.id}`} className="block truncate font-medium hover:underline">
                    {d.name}
                  </Link>
                  <span className="block truncate text-xs text-muted">
                    {latest?.source_file?.original_filename ?? "-"} · rev {latest?.revision_number ?? "-"}
                  </span>
                </TD>
                <TD>{latest ? <RevisionStatusBadge status={latest.status} /> : null}</TD>
                <TD className="hidden text-right font-mono text-xs tabular-nums md:table-cell">{counts.component_count ?? "-"}</TD>
                <TD className="hidden text-right font-mono text-xs tabular-nums md:table-cell">{counts.net_count ?? "-"}</TD>
                <TD className="hidden text-right font-mono text-xs tabular-nums lg:table-cell">
                  {counts.copper_layer_count !== undefined ? `${counts.copper_layer_count} Cu / ${counts.layer_count}` : "-"}
                </TD>
                <TD className="text-right text-xs whitespace-nowrap text-muted" title={formatDateTime(d.updated_at)}>
                  {relativeTime(d.updated_at)}
                </TD>
              </TR>
            );
          })}
        </TBody>
      </Table>
    </Card>
  );
}
