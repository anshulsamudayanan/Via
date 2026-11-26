"use client";

import { Button, Kbd, Panel } from "@via/ui";
import { ArrowRight, Plus, Search } from "lucide-react";
import Link from "next/link";
import { useRouter } from "next/navigation";

import { ActivityList } from "@/components/activity-list";
import { useApi } from "@/components/api-context";
import { PageHeader } from "@/components/app-shell";
import { OverviewStrip } from "@/components/dashboard/overview-strip";
import { ProjectsPanel } from "@/components/dashboard/projects-panel";
import { UploadShortcut } from "@/components/designs/upload-shortcut";
import { NewProjectDialog } from "@/components/projects/new-project-dialog";
import { useOpenCommandMenu } from "@/components/shell/command-menu";
import { useAsync } from "@/lib/use-async";

export default function DashboardPage() {
  const client = useApi();
  const router = useRouter();
  const openSearch = useOpenCommandMenu();
  const summary = useAsync((s) => client.projects.summary(s), [client]);
  const isNew = summary.data !== undefined && summary.data.active + summary.data.archived === 0;
  const goTo = (id: string) => router.push(`/projects/${id}`);

  return (
    <>
      <PageHeader
        title="Dashboard"
        description="Projects, PCB designs and engineering activity you have access to."
        actions={
          <>
            <Button variant="secondary" onClick={openSearch} className="hidden text-muted md:inline-flex" aria-keyshortcuts="Meta+K Control+K">
              <Search /> Search <Kbd className="ml-2">⌘K</Kbd>
            </Button>
            {isNew ? null : <UploadShortcut />}
            <NewProjectDialog onCreated={(p) => goTo(p.id)} />
          </>
        }
      />

      {isNew ? (
        <div className="grid items-start gap-4 lg:grid-cols-[minmax(0,1fr)_360px]">
          <Panel title="Get started">
            <div className="space-y-3 px-4 py-4 text-[13px] text-muted">
              <ol className="list-decimal space-y-1.5 pl-5">
                <li>
                  <span className="text-foreground">Create a project</span>: a private workspace for one board or product.
                </li>
                <li>
                  <span className="text-foreground">Upload a KiCad board</span>: a <code className="font-mono text-[12.5px] text-foreground">.kicad_pcb</code> file, or a zipped project
                  with its <code className="font-mono text-[12.5px] text-foreground">.kicad_pro</code> design rules.
                </li>
                <li>
                  <span className="text-foreground">Run an analysis</span> on the design to get deterministic findings with evidence.
                </li>
              </ol>
              <NewProjectDialog
                onCreated={(p) => goTo(p.id)}
                trigger={
                  <Button variant="primary">
                    <Plus /> New project
                  </Button>
                }
              />
            </div>
          </Panel>
          <Panel title="Activity">
            <ActivityList pageSize={6} preview engineeringOnly />
          </Panel>
        </div>
      ) : (
        <div className="space-y-4">
          <OverviewStrip data={summary.data} error={summary.error} onRetry={summary.reload} />
          <div className="grid items-start gap-4 xl:grid-cols-[minmax(0,1fr)_360px]">
            <ProjectsPanel />
            <Panel
              title="Activity"
              actions={
                <Link href="/activity" className="inline-flex items-center gap-1 text-xs text-muted hover:text-foreground">
                  View all <ArrowRight className="size-3" aria-hidden="true" />
                </Link>
              }
            >
              <ActivityList pageSize={8} preview engineeringOnly />
            </Panel>
          </div>
        </div>
      )}
    </>
  );
}
