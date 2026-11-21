"use client";

import { Button, Card, CardContent, CardHeader, CardTitle, EmptyState, ErrorState, Skeleton, Tooltip } from "@via/ui";
import { ArrowRight, FolderKanban, FolderPlus, Plus, Upload } from "lucide-react";
import Link from "next/link";
import { useRouter } from "next/navigation";

import { ActivityList } from "@/components/activity-list";
import { useApi } from "@/components/api-context";
import { PageHeader } from "@/components/app-shell";
import { RoleBadge } from "@/components/projects/badges";
import { NewProjectDialog } from "@/components/projects/new-project-dialog";
import { useSession } from "@/components/session";
import { errorMessage } from "@/lib/errors";
import { relativeTime } from "@/lib/format";
import { useAsync } from "@/lib/use-async";

function Stat({ label, value, href }: { label: string; value: number | undefined; href: string }) {
  return (
    <Link href={href} className="rounded-lg border border-border bg-surface px-4 py-3 transition-colors hover:bg-surface-hover">
      <div className="text-xs text-muted">{label}</div>
      <div className="mt-0.5 font-mono text-xl font-semibold tabular-nums">
        {value === undefined ? <Skeleton className="mt-1 h-6 w-10" /> : value}
      </div>
    </Link>
  );
}

export default function DashboardPage() {
  const client = useApi();
  const router = useRouter();
  const { me } = useSession();
  const summary = useAsync(() => client.projects.summary(), [client]);
  const recent = useAsync((signal) => client.projects.list({ sort: "updated", limit: 5 }, signal), [client]);
  const firstName = me.user.display_name.split(/\s+/)[0];
  const isNew = summary.data && summary.data.active + summary.data.archived === 0;
  const goTo = (id: string) => router.push(`/projects/${id}`);

  return (
    <>
      <PageHeader
        title={`Welcome${isNew ? "" : " back"}, ${firstName}`}
        description="Your projects and recent activity."
        actions={
          <>
            <Tooltip content="PCB upload arrives in the next update.">
              <span tabIndex={0} className="rounded-md">
                <Button variant="secondary" disabled aria-label="Upload PCB (coming soon)">
                  <Upload /> Upload PCB
                </Button>
              </span>
            </Tooltip>
            <NewProjectDialog onCreated={(p) => goTo(p.id)} />
          </>
        }
      />

      {summary.error ? <ErrorState className="mb-4" title="Couldn't load your projects" description={errorMessage(summary.error)} /> : null}

      {isNew ? (
        <Card>
          <EmptyState
            icon={<FolderPlus />}
            title="Create your first project"
            description="A project is a private workspace for a PCB design. You'll be able to upload KiCad boards into it and inspect them."
            action={
              <NewProjectDialog
                onCreated={(p) => goTo(p.id)}
                trigger={
                  <Button variant="primary">
                    <Plus /> New project
                  </Button>
                }
              />
            }
          />
        </Card>
      ) : (
        <div className="space-y-4">
          <div className="grid grid-cols-2 gap-3 sm:grid-cols-4">
            <Stat label="Active projects" value={summary.data?.active} href="/projects" />
            <Stat label="Archived projects" value={summary.data?.archived} href="/projects?status=archived" />
          </div>
          <div className="grid gap-4 lg:grid-cols-5">
            <Card className="lg:col-span-3">
              <CardHeader>
                <CardTitle>Recent projects</CardTitle>
                <Link href="/projects" className="inline-flex items-center gap-1 text-xs text-muted hover:text-foreground">
                  All projects <ArrowRight className="size-3" aria-hidden="true" />
                </Link>
              </CardHeader>
              {recent.loading && !recent.data ? (
                <CardContent className="space-y-2">
                  {Array.from({ length: 3 }, (_, i) => (
                    <Skeleton key={i} className="h-9 w-full" />
                  ))}
                </CardContent>
              ) : recent.data && recent.data.items.length > 0 ? (
                <ul className="divide-y divide-border">
                  {recent.data.items.map((p) => (
                    <li key={p.id}>
                      <Link href={`/projects/${p.id}`} className="flex items-center gap-3 px-4 py-2.5 hover:bg-surface-hover">
                        <FolderKanban className="size-4 shrink-0 text-subtle" aria-hidden="true" />
                        <span className="min-w-0 flex-1">
                          <span className="block truncate text-sm font-medium">{p.name}</span>
                          <span className="block truncate text-xs text-muted">{p.description || "No description"}</span>
                        </span>
                        <RoleBadge role={p.my_role} />
                        <span className="hidden w-24 text-right text-xs text-subtle sm:block">{relativeTime(p.updated_at)}</span>
                      </Link>
                    </li>
                  ))}
                </ul>
              ) : (
                <EmptyState title="No active projects" description="Archived projects are listed on the Projects page." />
              )}
            </Card>
            <Card className="lg:col-span-2">
              <CardHeader>
                <CardTitle>Recent activity</CardTitle>
                <Link href="/activity" className="inline-flex items-center gap-1 text-xs text-muted hover:text-foreground">
                  View all <ArrowRight className="size-3" aria-hidden="true" />
                </Link>
              </CardHeader>
              <ActivityList pageSize={8} preview />
            </Card>
          </div>
        </div>
      )}
    </>
  );
}
