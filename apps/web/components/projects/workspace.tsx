"use client";

import { ApiError } from "@via/api-client";
import type { Project } from "@via/types";
import { Button, Card, CardContent, CardHeader, CardTitle, cn, EmptyState, ErrorState, Skeleton } from "@via/ui";
import { Archive, BarChart3, Cpu, FileStack, FolderX, Layers } from "lucide-react";
import Link from "next/link";
import { useParams, usePathname, useSearchParams } from "next/navigation";

import { ActivityList } from "@/components/activity-list";
import { useApi } from "@/components/api-context";
import { ComingSoon } from "@/components/coming-soon";
import { ArchivedBadge, RoleBadge, VisibilityBadge } from "@/components/projects/badges";
import { ProjectSettings } from "@/components/projects/project-settings";
import { errorMessage } from "@/lib/errors";
import { formatDateTime } from "@/lib/format";
import { useAsync } from "@/lib/use-async";

export const TABS = [
  { id: "overview", label: "Overview" },
  { id: "designs", label: "PCB Designs" },
  { id: "files", label: "Files" },
  { id: "components", label: "Components" },
  { id: "analysis", label: "Analysis" },
  { id: "activity", label: "Activity" },
  { id: "settings", label: "Settings" },
] as const;

export type TabId = (typeof TABS)[number]["id"];

export function ProjectWorkspace() {
  const client = useApi();
  const { projectId } = useParams<{ projectId: string }>();
  const params = useSearchParams();
  const pathname = usePathname();
  const tab = (TABS.find((t) => t.id === params.get("tab"))?.id ?? "overview") as TabId;
  const project = useAsync((signal) => client.projects.get(projectId, signal), [client, projectId]);

  if (project.error) {
    if (project.error instanceof ApiError && (project.error.status === 404 || project.error.status === 422)) {
      return (
        <EmptyState
          icon={<FolderX />}
          title="Project not found"
          description="It may have been deleted, or you don't have access to it."
          action={
            <Button asChild size="sm">
              <Link href="/projects">Back to projects</Link>
            </Button>
          }
        />
      );
    }
    return <ErrorState title="Couldn't load this project" description={errorMessage(project.error)} action={<Button size="sm" onClick={project.reload}>Retry</Button>} />;
  }
  if (!project.data) {
    return (
      <div className="space-y-3">
        <Skeleton className="h-7 w-64" />
        <Skeleton className="h-8 w-full" />
        <Skeleton className="h-40 w-full" />
      </div>
    );
  }
  const p = project.data;

  return (
    <div className="space-y-4">
      <div className="space-y-1">
        <div className="text-xs text-muted">
          <Link href="/projects" className="hover:text-foreground hover:underline">
            Projects
          </Link>{" "}
          / {p.organization.is_personal ? "Personal" : p.organization.name}
        </div>
        <div className="flex flex-wrap items-center gap-2">
          <h1 className="text-lg font-semibold tracking-tight">{p.name}</h1>
          <RoleBadge role={p.my_role} />
          <VisibilityBadge visibility={p.visibility} />
          <ArchivedBadge project={p} />
        </div>
      </div>

      {p.archived_at ? (
        <div role="status" className="flex items-center gap-2 rounded-md border border-border bg-surface-raised px-3 py-2 text-sm text-muted">
          <Archive className="size-4" aria-hidden="true" />
          This project was archived {formatDateTime(p.archived_at)}. It&apos;s read-only until it&apos;s restored.
        </div>
      ) : null}

      <nav aria-label="Project sections" className="-mx-1 flex gap-0.5 overflow-x-auto border-b border-border px-1">
        {TABS.map((t) => (
          <Link
            key={t.id}
            href={t.id === "overview" ? pathname : `${pathname}?tab=${t.id}`}
            aria-current={tab === t.id ? "page" : undefined}
            className={cn(
              "-mb-px border-b-2 px-2.5 py-2 text-sm whitespace-nowrap transition-colors",
              tab === t.id ? "border-accent font-medium text-foreground" : "border-transparent text-muted hover:text-foreground",
            )}
          >
            {t.label}
          </Link>
        ))}
      </nav>

      <TabPanel tab={tab} project={p} onChange={project.setData} />
    </div>
  );
}

function TabPanel({ tab, project, onChange }: { tab: TabId; project: Project; onChange: (p: Project) => void }) {
  switch (tab) {
    case "overview":
      return <Overview project={project} />;
    case "designs":
      return (
        <ComingSoon
          icon={<Layers />}
          title="PCB designs"
          description="Upload KiCad boards (.kicad_pcb) to this project. Each upload is validated, parsed and stored as a revision. Arrives in the next update."
        />
      );
    case "files":
      return (
        <ComingSoon
          icon={<FileStack />}
          title="Files"
          description="Original uploads and their metadata (size, SHA-256, upload time) will be listed here once PCB upload is available."
        />
      );
    case "components":
      return (
        <ComingSoon
          icon={<Cpu />}
          title="Components"
          description="Footprints extracted from parsed boards (references, values, positions) will be searchable here after the first upload."
        />
      );
    case "analysis":
      return (
        <ComingSoon
          icon={<BarChart3 />}
          title="Analysis"
          description="Design analysis is planned for a later stage. VIA will never show analysis results it hasn't actually computed."
        />
      );
    case "activity":
      return (
        <Card>
          <ActivityList projectId={project.id} showProject={false} />
        </Card>
      );
    case "settings":
      return <ProjectSettings project={project} onChange={onChange} />;
  }
}

function Overview({ project }: { project: Project }) {
  const rows: [string, string][] = [
    ["Owner", project.owner.display_name],
    ["Organization", project.organization.is_personal ? "Personal workspace" : project.organization.name],
    ["Your role", project.my_role.charAt(0).toUpperCase() + project.my_role.slice(1)],
    ["Visibility", project.visibility === "private" ? "Private" : "Organization"],
    ["Created", formatDateTime(project.created_at)],
    ["Last updated", formatDateTime(project.updated_at)],
  ];
  return (
    <div className="grid gap-4 lg:grid-cols-3">
      <Card className="lg:col-span-2">
        <CardHeader>
          <CardTitle>About</CardTitle>
        </CardHeader>
        <CardContent>
          {project.description ? (
            <p className="text-sm leading-relaxed whitespace-pre-wrap">{project.description}</p>
          ) : (
            <p className="text-sm text-muted">
              No description.{" "}
              {project.my_role !== "viewer" ? (
                <Link href="?tab=settings" className="text-accent hover:underline">
                  Add one in settings
                </Link>
              ) : null}
            </p>
          )}
        </CardContent>
        <div className="grid grid-cols-2 border-t border-border sm:grid-cols-3">
          <div className="px-4 py-3">
            <div className="text-xs text-muted">PCB designs</div>
            <div className="font-mono text-lg tabular-nums">{project.design_count}</div>
          </div>
        </div>
      </Card>
      <Card>
        <CardHeader>
          <CardTitle>Details</CardTitle>
        </CardHeader>
        <dl className="divide-y divide-border text-sm">
          {rows.map(([k, v]) => (
            <div key={k} className="flex justify-between gap-3 px-4 py-2">
              <dt className="text-muted">{k}</dt>
              <dd className="truncate text-right">{v}</dd>
            </div>
          ))}
        </dl>
      </Card>
    </div>
  );
}
