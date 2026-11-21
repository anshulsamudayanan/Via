"use client";

import { ApiError } from "@via/api-client";
import { Button, EmptyState, ErrorState, Skeleton } from "@via/ui";
import { ArrowLeft, FolderX } from "lucide-react";
import Link from "next/link";
import { useParams, useSearchParams } from "next/navigation";
import { Suspense } from "react";

import { useApi } from "@/components/api-context";
import { BoardViewer } from "@/components/viewer/board-viewer";
import { errorMessage } from "@/lib/errors";
import { useAsync } from "@/lib/use-async";

function FullViewer() {
  const client = useApi();
  const { projectId, designId } = useParams<{ projectId: string; designId: string }>();
  const revisionId = useSearchParams().get("revision") ?? undefined;
  const design = useAsync((s) => client.designs.get(designId, s), [client, designId]);
  const back = `/projects/${projectId}/designs/${designId}${revisionId ? `?revision=${revisionId}` : ""}`;

  if (design.error) {
    if (design.error instanceof ApiError && design.error.status === 404) {
      return <EmptyState icon={<FolderX />} title="Design not found" description="It may have been deleted, or you don't have access to it." />;
    }
    return <ErrorState title="Couldn't load this design" description={errorMessage(design.error)} />;
  }
  if (!design.data) return <Skeleton className="h-[70vh] w-full" />;
  const d = design.data;
  const revision = revisionId ? d.revisions.find((r) => r.id === revisionId) : d.current_revision;

  return (
    <div className="flex h-[calc(100dvh-3rem)] flex-col gap-3 md:h-[calc(100dvh-3rem)]">
      <div className="flex items-center gap-3">
        <Button asChild size="sm" variant="ghost">
          <Link href={back}>
            <ArrowLeft /> Back
          </Link>
        </Button>
        <h1 className="truncate text-sm font-semibold">{d.name}</h1>
        {revision ? <span className="text-xs text-muted">Revision {revision.revision_number}</span> : null}
      </div>
      {revision && revision.status === "ready" ? (
        <BoardViewer designId={d.id} revisionId={revisionId} designName={d.name} className="min-h-0 flex-1" />
      ) : (
        <EmptyState title="No parsed revision to show" description="Upload a board that parses successfully to view it here." />
      )}
    </div>
  );
}

export default function ViewerPage() {
  return (
    <Suspense>
      <FullViewer />
    </Suspense>
  );
}
