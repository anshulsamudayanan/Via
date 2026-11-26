"use client";

import type { ActivityItem } from "@via/types";
import { Button, cn, EmptyState, ErrorState, Skeleton } from "@via/ui";
import { CircuitBoard, FolderKanban, GitCommitHorizontal, History, ScanSearch, Sparkles, UserRound } from "lucide-react";
import Link from "next/link";
import { useState } from "react";

import { useApi } from "@/components/api-context";
import { activityFailed, type ActivityKind, activityKind, describeActivity } from "@/lib/activity";
import { errorMessage } from "@/lib/errors";
import { formatDateTime, relativeTime } from "@/lib/format";
import { useAsync } from "@/lib/use-async";

interface Props {
  projectId?: string;
  pageSize?: number;
  /** Show the project name next to each entry (global feed). */
  showProject?: boolean;
  /** Hide the "Load more" control (dashboard preview). */
  preview?: boolean;
  /** Hide account events (sign-ins, password changes): the dashboard shows engineering work only. */
  engineeringOnly?: boolean;
}

const ICONS: Record<ActivityKind, typeof History> = {
  account: UserRound,
  project: FolderKanban,
  design: CircuitBoard,
  analysis: ScanSearch,
  change: GitCommitHorizontal,
  ai: Sparkles,
};

/** One feed entry: what happened (first line), where and when (second line). */
export function ActivityEntry({ item, showProject = true }: { item: ActivityItem; showProject?: boolean }) {
  const Icon = ICONS[activityKind(item)];
  const failed = activityFailed(item);
  const designHref = item.project && item.target_type === "design" && item.target_id ? `/projects/${item.project.id}/designs/${item.target_id}` : null;
  const text = (
    <>
      <span className="font-medium text-foreground">{item.actor?.display_name ?? "Someone"}</span>{" "}
      <span className={failed ? "text-danger" : "text-muted"}>{describeActivity(item)}</span>
    </>
  );
  return (
    <li className="flex gap-3 px-4 py-2">
      <Icon aria-hidden="true" className={cn("mt-0.5 size-4 shrink-0", failed ? "text-danger" : "text-subtle")} />
      <div className="min-w-0 flex-1">
        <p className="text-[13px] leading-5">{designHref ? <Link href={designHref} className="hover:underline">{text}</Link> : text}</p>
        <p className="flex min-w-0 items-center gap-1.5 text-xs leading-4 text-subtle">
          {showProject && item.project ? (
            <>
              <Link href={`/projects/${item.project.id}`} className="truncate text-muted hover:text-foreground hover:underline">
                {item.project.name}
              </Link>
              <span aria-hidden="true">·</span>
            </>
          ) : null}
          <time dateTime={item.created_at} title={formatDateTime(item.created_at)} className="shrink-0 tabular-nums">
            {relativeTime(item.created_at)}
          </time>
        </p>
      </div>
    </li>
  );
}

export function ActivityList({ projectId, pageSize = 20, showProject = true, preview = false, engineeringOnly = false }: Props) {
  const client = useApi();
  const [extra, setExtra] = useState<ActivityItem[]>([]);
  const [loadingMore, setLoadingMore] = useState(false);
  // The API can't filter by type, so a filtered preview reads a larger page and trims it.
  const fetchSize = engineeringOnly ? Math.min(pageSize * 3, 100) : pageSize;
  const first = useAsync(() => client.activity.list({ project_id: projectId, limit: fetchSize }), [client, projectId, fetchSize]);

  if (first.loading && !first.data) {
    return (
      <div className="space-y-3 p-4" aria-busy="true">
        {Array.from({ length: Math.min(pageSize, 5) }, (_, i) => (
          <Skeleton key={i} className="h-8 w-full" />
        ))}
      </div>
    );
  }
  if (first.error) {
    return (
      <ErrorState
        className="m-4"
        title="Couldn't load activity"
        description={errorMessage(first.error)}
        action={
          <Button size="sm" onClick={first.reload}>
            Retry
          </Button>
        }
      />
    );
  }
  const all = [...(first.data?.items ?? []), ...extra];
  const items = (engineeringOnly ? all.filter((i) => activityKind(i) !== "account") : all).slice(0, preview ? pageSize : undefined);
  if (items.length === 0) {
    return (
      <EmptyState
        icon={<History />}
        title="No activity yet"
        description={engineeringOnly ? "Uploads, imports and analyses in your projects will appear here." : "Changes to your projects will appear here."}
      />
    );
  }
  const total = first.data?.total ?? 0;

  async function loadMore() {
    setLoadingMore(true);
    try {
      const page = await client.activity.list({ project_id: projectId, limit: pageSize, offset: all.length });
      setExtra((e) => [...e, ...page.items]);
    } finally {
      setLoadingMore(false);
    }
  }

  return (
    <div>
      <ol className="divide-y divide-border">
        {items.map((item) => (
          <ActivityEntry key={item.id} item={item} showProject={showProject} />
        ))}
      </ol>
      {!preview && all.length < total ? (
        <div className="border-t border-border p-2 text-center">
          <Button size="sm" variant="ghost" onClick={() => void loadMore()} disabled={loadingMore}>
            {loadingMore ? "Loading…" : `Load more (${total - all.length} remaining)`}
          </Button>
        </div>
      ) : null}
    </div>
  );
}
