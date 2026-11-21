import type { RevisionStatus } from "@via/types";
import { Badge } from "@via/ui";

const LABEL: Record<RevisionStatus, { text: string; tone: "neutral" | "accent" | "success" | "danger" }> = {
  pending: { text: "Queued", tone: "neutral" },
  processing: { text: "Parsing", tone: "accent" },
  ready: { text: "Parsed", tone: "success" },
  failed: { text: "Failed", tone: "danger" },
};

export function RevisionStatusBadge({ status }: { status: RevisionStatus }) {
  const { text, tone } = LABEL[status];
  return <Badge tone={tone}>{text}</Badge>;
}

export const isTerminal = (status: RevisionStatus) => status === "ready" || status === "failed";
