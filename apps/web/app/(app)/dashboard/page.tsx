"use client";

import type { DesignListItem, Project } from "@via/types";
import { Button, ErrorState, Panel, Skeleton, useToast } from "@via/ui";
import { ArrowRight, Upload } from "lucide-react";
import Link from "next/link";
import { useRouter } from "next/navigation";
import { type ReactNode, useRef } from "react";

import { ActivityList } from "@/components/activity-list";
import { useApi } from "@/components/api-context";
import { BoardDropzone, type BoardDropzoneHandle } from "@/components/dashboard/board-dropzone";
import { BoardHero } from "@/components/dashboard/board-hero";
import { FindingsChart } from "@/components/dashboard/findings-chart";
import { FirstRun } from "@/components/dashboard/first-run";
import { ProjectsPanel } from "@/components/dashboard/projects-panel";
import { StatCards } from "@/components/dashboard/stat-cards";
import { NewProjectDialog } from "@/components/projects/new-project-dialog";
import { errorMessage } from "@/lib/errors";
import { useAsync } from "@/lib/use-async";

/** Every design you can see (paged, 100 at a time): for the revision total and the latest board. */
async function allDesigns(list: (offset: number, signal: AbortSignal) => Promise<{ items: DesignListItem[]; total: number }>, signal: AbortSignal) {
  const items: DesignListItem[] = [];
  for (let offset = 0; offset < 1000; offset += 100) {
    const page = await list(offset, signal);
    items.push(...page.items);
    if (items.length >= page.total || page.items.length === 0) break;
  }
  return items;
}

export default function DashboardPage() {
  const client = useApi();
  const router = useRouter();
  const { push } = useToast();
  const dropzone = useRef<BoardDropzoneHandle>(null);

  const summary = useAsync((s) => client.projects.summary(s), [client]);
  const isNew = summary.data !== undefined && summary.data.active + summary.data.archived === 0;
  const findings = useAsync((s) => client.analysis.browseFindings({ status: "open", limit: 1 }, s), [client]);
  const runs = useAsync((s) => client.analysis.browseRuns({ limit: 100 }, s), [client]);
  const designs = useAsync((s) => allDesigns((offset, sig) => client.designs.browse({ sort: "updated", limit: 100, offset }, sig), s), [client]);

  const revisions = designs.data?.reduce((n, d) => n + d.revision_count, 0);
  const lastRun = runs.data ? (runs.data.items[0] ?? null) : undefined;
  // The newest design whose current revision parsed (a failed upload has no counts to show).
  const latestBoard = designs.data ? (designs.data.find((d) => d.current_revision?.status === "ready") ?? designs.data[0] ?? null) : undefined;

  function onCreated(p: Project) {
    push({ tone: "success", title: "Project created", description: `${p.name} is private: only you can see it until you invite people.` });
    router.push(`/projects/${p.id}`);
  }
  const newProject = (trigger?: ReactNode) => <NewProjectDialog onCreated={onCreated} trigger={trigger ?? <Button variant="primary">New project</Button>} />;

  return (
    <>
      {/* Page title and the workspace in one line of facts */}
      <div className="mb-8 flex flex-wrap items-end justify-between gap-x-4 gap-y-4">
        <div className="min-w-0">
          <h1 className="font-display text-[32px] font-normal leading-[1.1] tracking-[-0.02em] text-foreground sm:text-[36px]">Dashboard</h1>
          <p className="mt-2 text-[14px] text-muted">
            {summary.data ? (
              isNew ? (
                "Upload a KiCad board to get deterministic, evidence-backed findings."
              ) : (
                <>
                  {summary.data.active} active {summary.data.active === 1 ? "project" : "projects"} · {summary.data.designs} PCB {summary.data.designs === 1 ? "design" : "designs"} ·{" "}
                  {summary.data.analyses_7d} {summary.data.analyses_7d === 1 ? "analysis" : "analyses"} in the last 7 days
                </>
              )
            ) : (
              <Skeleton className="inline-block h-4 w-72 max-w-full align-middle" />
            )}
          </p>
        </div>
        <div className="flex flex-wrap items-center gap-2">
          {isNew ? null : (
            <Button
              variant="secondary"
              onClick={() => {
                document.getElementById("board-dropzone")?.scrollIntoView({ block: "nearest", behavior: "smooth" });
                dropzone.current?.browse();
              }}
            >
              <Upload /> Upload board
            </Button>
          )}
          {newProject()}
        </div>
      </div>

      {isNew ? (
        <FirstRun newProject={(trigger) => newProject(trigger)} />
      ) : (
        <div className="space-y-4">
          {summary.error ? (
            <ErrorState
              title="Couldn't load the overview"
              description={errorMessage(summary.error)}
              action={
                <Button size="sm" onClick={summary.reload}>
                  Retry
                </Button>
              }
            />
          ) : null}
          <StatCards summary={summary.data} findings={findings.data} revisions={revisions} lastRun={lastRun} />
          <div className="grid gap-4 pt-4 lg:grid-cols-[minmax(0,340px)_minmax(0,1fr)]">
            <BoardHero latest={latestBoard} />
            <FindingsChart runs={runs.data?.items} />
          </div>
          <div className="grid items-start gap-4 xl:grid-cols-[minmax(0,1fr)_340px]">
            <ProjectsPanel />
            <div className="grid gap-4 md:grid-cols-2 xl:grid-cols-1">
              <Panel title="Upload a board">
                <div className="p-3">
                  <BoardDropzone ref={dropzone} />
                </div>
              </Panel>
              <Panel
                title="Activity"
                actions={
                  <Link href="/activity" className="inline-flex items-center gap-1 rounded-sm text-xs text-muted hover:text-foreground">
                    View all <ArrowRight className="size-3" aria-hidden="true" />
                  </Link>
                }
              >
                <ActivityList pageSize={6} preview engineeringOnly />
              </Panel>
            </div>
          </div>
        </div>
      )}
    </>
  );
}
