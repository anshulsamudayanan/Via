"use client";

import type { ActivityItem } from "@via/types";
import { Button, EmptyState, ErrorState, Skeleton } from "@via/ui";
import { History } from "lucide-react";
import Link from "next/link";
import { useState } from "react";

import { useApi } from "@/components/api-context";
import { describeActivity } from "@/lib/activity";
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
}

export function ActivityList({ projectId, pageSize = 20, showProject = true, preview = false }: Props) {
  const client = useApi();
  const [extra, setExtra] = useState<ActivityItem[]>([]);
  const [loadingMore, setLoadingMore] = useState(false);
  const first = useAsync(() => client.activity.list({ project_id: projectId, limit: pageSize }), [client, projectId, pageSize]);

  if (first.loading && !first.data) {
    return (
      <div className="space-y-2 p-4">
        {Array.from({ length: 4 }, (_, i) => (
          <Skeleton key={i} className="h-5 w-full" />
        ))}
      </div>
    );
  }
  if (first.error) {
    return <ErrorState className="m-4" title="Couldn't load activity" description={errorMessage(first.error)} />;
  }
  const items = [...(first.data?.items ?? []), ...extra];
  if (items.length === 0) {
    return <EmptyState icon={<History />} title="No activity yet" description="Changes to your projects will appear here." />;
  }
  const total = first.data?.total ?? 0;

  async function loadMore() {
    setLoadingMore(true);
    try {
      const page = await client.activity.list({ project_id: projectId, limit: pageSize, offset: items.length });
      setExtra((e) => [...e, ...page.items]);
    } finally {
      setLoadingMore(false);
    }
  }

  return (
    <div>
      <ol className="divide-y divide-border">
        {items.map((item) => (
          <li key={item.id} className="flex items-baseline justify-between gap-3 px-4 py-2 text-sm">
            <p className="min-w-0">
              <span className="font-medium text-foreground">{item.actor?.display_name ?? "Someone"}</span>{" "}
              <span className="text-muted">{describeActivity(item)}</span>
              {showProject && item.project ? (
                <>
                  {" "}
                  <span className="text-subtle">in</span>{" "}
                  <Link href={`/projects/${item.project.id}`} className="text-foreground hover:underline">
                    {item.project.name}
                  </Link>
                </>
              ) : null}
            </p>
            <time dateTime={item.created_at} title={formatDateTime(item.created_at)} className="shrink-0 text-xs text-subtle tabular-nums">
              {relativeTime(item.created_at)}
            </time>
          </li>
        ))}
      </ol>
      {!preview && items.length < total ? (
        <div className="border-t border-border p-2 text-center">
          <Button size="sm" variant="ghost" onClick={() => void loadMore()} disabled={loadingMore}>
            {loadingMore ? "Loading..." : `Load more (${total - items.length} remaining)`}
          </Button>
        </div>
      ) : null}
    </div>
  );
}
