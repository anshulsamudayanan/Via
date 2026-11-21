"use client";

import type { Project } from "@via/types";
import { EmptyState, ErrorState, Field, Select, Skeleton } from "@via/ui";
import { Cpu } from "lucide-react";
import { useState } from "react";

import { useApi } from "@/components/api-context";
import { ComponentsTable } from "@/components/designs/data-tables";
import { DesignsList } from "@/components/designs/designs-list";
import { UploadPanel } from "@/components/designs/upload-panel";
import { errorMessage } from "@/lib/errors";
import { useAsync } from "@/lib/use-async";

export function DesignsSection({ project, onChanged }: { project: Project; onChanged?: () => void }) {
  const client = useApi();
  const designs = useAsync((s) => client.designs.list(project.id, s), [client, project.id]);
  const canUpload = project.my_role !== "viewer" && !project.archived_at;
  const refresh = () => {
    designs.reload();
    onChanged?.();
  };
  return (
    <div className="space-y-4">
      {canUpload ? <UploadPanel projectId={project.id} onUploaded={refresh} onSettled={refresh} /> : null}
      {designs.error ? (
        <ErrorState title="Couldn't load designs" description={errorMessage(designs.error)} />
      ) : !designs.data ? (
        <Skeleton className="h-32 w-full" />
      ) : (
        <DesignsList projectId={project.id} designs={designs.data} />
      )}
    </div>
  );
}

export function ProjectComponentsSection({ project }: { project: Project }) {
  const client = useApi();
  const designs = useAsync((s) => client.designs.list(project.id, s), [client, project.id]);
  const parsed = (designs.data ?? []).filter((d) => d.current_revision);
  const [selected, setSelected] = useState<string | null>(null);
  const designId = selected ?? parsed[0]?.id ?? null;

  if (designs.error) return <ErrorState title="Couldn't load designs" description={errorMessage(designs.error)} />;
  if (!designs.data) return <Skeleton className="h-32 w-full" />;
  if (!designId) {
    return <EmptyState icon={<Cpu />} title="No parsed designs yet" description="Components appear here after a KiCad board in this project has been parsed." />;
  }
  return (
    <div className="space-y-3">
      {parsed.length > 1 ? (
        <Field label="Design" className="max-w-xs">
          {(p) => (
            <Select {...p} value={designId} onChange={(e) => setSelected(e.target.value)}>
              {parsed.map((d) => (
                <option key={d.id} value={d.id}>
                  {d.name} (rev {d.current_revision?.revision_number})
                </option>
              ))}
            </Select>
          )}
        </Field>
      ) : null}
      <ComponentsTable key={designId} designId={designId} />
    </div>
  );
}
