import type { Project, ProjectRole, ProjectVisibility } from "@via/types";
import { Badge, Tooltip } from "@via/ui";
import { Archive, Building2, Lock } from "lucide-react";

const ROLE_LABEL: Record<ProjectRole, string> = { owner: "Owner", editor: "Editor", viewer: "Viewer" };

export function RoleBadge({ role }: { role: ProjectRole }) {
  return <Badge tone={role === "owner" ? "accent" : "neutral"}>{ROLE_LABEL[role]}</Badge>;
}

export function VisibilityBadge({ visibility }: { visibility: ProjectVisibility }) {
  return visibility === "private" ? (
    <Tooltip content="Only the owner and invited members can see this project.">
      <Badge>
        <Lock className="size-3" aria-hidden="true" /> Private
      </Badge>
    </Tooltip>
  ) : (
    <Tooltip content="Members of the owning organization can view this project.">
      <Badge tone="warning">
        <Building2 className="size-3" aria-hidden="true" /> Organization
      </Badge>
    </Tooltip>
  );
}

export function ArchivedBadge({ project }: { project: Pick<Project, "archived_at"> }) {
  if (!project.archived_at) return null;
  return (
    <Badge>
      <Archive className="size-3" aria-hidden="true" /> Archived
    </Badge>
  );
}
