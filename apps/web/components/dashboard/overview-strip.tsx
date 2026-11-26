import type { ProjectSummary } from "@via/types";
import { Button, ErrorState, Skeleton } from "@via/ui";
import Link from "next/link";

import { errorMessage } from "@/lib/errors";

interface Cell {
  label: string;
  value: (s: ProjectSummary) => number;
  href: string;
  hint: string;
}

const CELLS: Cell[] = [
  { label: "Active projects", value: (s) => s.active, href: "/projects", hint: "Projects you can access that aren't archived" },
  { label: "PCB designs", value: (s) => s.designs, href: "/projects", hint: "Designs in your active projects" },
  { label: "Imports · 7 days", value: (s) => s.imports_7d, href: "/activity", hint: "Board uploads in the last 7 days" },
  { label: "Analyses · 7 days", value: (s) => s.analyses_7d, href: "/activity", hint: "Analysis runs completed or failed in the last 7 days" },
];

/** Four real counts in one bordered strip. Every number comes from GET /projects/summary. */
export function OverviewStrip({ data, error, onRetry }: { data: ProjectSummary | undefined; error: unknown; onRetry: () => void }) {
  if (error) {
    return (
      <ErrorState
        title="Couldn't load the overview"
        description={errorMessage(error)}
        action={
          <Button size="sm" onClick={onRetry}>
            Retry
          </Button>
        }
      />
    );
  }
  return (
    <dl className="grid grid-cols-2 overflow-hidden rounded-lg border border-border bg-surface lg:grid-cols-4">
      {CELLS.map((cell, i) => (
        <div
          key={cell.label}
          className={[
            "border-border",
            i % 2 === 1 ? "border-l" : "",
            i >= 2 ? "border-t lg:border-t-0" : "",
            i === 2 ? "lg:border-l" : "",
          ].join(" ")}
        >
          <Link href={cell.href} title={cell.hint} className="flex h-full flex-col gap-0.5 px-4 py-2.5 transition-colors duration-100 hover:bg-surface-hover">
            <dt className="text-xs text-muted">{cell.label}</dt>
            <dd className="font-mono text-lg font-medium leading-7 tabular-nums text-foreground">
              {data ? cell.value(data) : <Skeleton className="my-1 h-5 w-10" />}
            </dd>
          </Link>
        </div>
      ))}
    </dl>
  );
}
