"use client";

import type { Project, ProjectSummary } from "@via/types";
import { Button, Kbd, Panel, Skeleton, useToast } from "@via/ui";
import { ArrowRight, Search, Upload } from "lucide-react";
import Link from "next/link";
import { useRouter } from "next/navigation";
import { type ReactNode, useRef } from "react";

import { ActivityList } from "@/components/activity-list";
import { useApi } from "@/components/api-context";
import { PageHeader } from "@/components/app-shell";
import { BoardDropzone, type BoardDropzoneHandle } from "@/components/dashboard/board-dropzone";
import { FirstRun } from "@/components/dashboard/first-run";
import { OverviewStrip } from "@/components/dashboard/overview-strip";
import { ProjectsPanel } from "@/components/dashboard/projects-panel";
import { NewProjectDialog } from "@/components/projects/new-project-dialog";
import { useOpenCommandMenu } from "@/components/shell/command-menu";
import { useAsync } from "@/lib/use-async";

function plural(n: number, one: string, many = `${one}s`) {
  return `${n} ${n === 1 ? one : many}`;
}

/** One line of real context under the title; a fixed-height skeleton until the summary arrives. */
function ContextLine({ data }: { data: ProjectSummary | undefined }) {
  if (!data) return <Skeleton className="mt-1 h-4 w-72 max-w-full" />;
  if (data.active + data.archived === 0) return <>Upload a KiCad board to get deterministic, evidence-backed findings.</>;
  return (
    <>
      {plural(data.active, "active project")} · {plural(data.designs, "PCB design")} · {plural(data.analyses_7d, "analysis", "analyses")} in the last 7 days
    </>
  );
}

export default function DashboardPage() {
  const client = useApi();
  const router = useRouter();
  const { push } = useToast();
  const openSearch = useOpenCommandMenu();
  const dropzone = useRef<BoardDropzoneHandle>(null);
  const summary = useAsync((s) => client.projects.summary(s), [client]);
  const isNew = summary.data !== undefined && summary.data.active + summary.data.archived === 0;

  function onCreated(p: Project) {
    push({ tone: "success", title: "Project created", description: `${p.name} is private: only you can see it until you invite people.` });
    router.push(`/projects/${p.id}`);
  }
  const newProject = (trigger?: ReactNode) => <NewProjectDialog onCreated={onCreated} trigger={trigger} />;

  return (
    <>
      <PageHeader
        title="Dashboard"
        description={<ContextLine data={summary.data} />}
        actions={
          <>
            <Button variant="secondary" onClick={openSearch} className="hidden text-muted md:inline-flex" aria-keyshortcuts="Meta+K Control+K">
              <Search /> Search <Kbd className="ml-2">⌘K</Kbd>
            </Button>
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
          </>
        }
      />

      {isNew ? (
        <FirstRun newProject={newProject} />
      ) : (
        <div className="space-y-4">
          <OverviewStrip data={summary.data} error={summary.error} onRetry={summary.reload} />
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
