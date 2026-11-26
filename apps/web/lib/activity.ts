import type { ActivityItem } from "@via/types";

type Describer = (item: ActivityItem) => string;

const str = (v: unknown) => (typeof v === "string" ? v : "");
const num = (v: unknown) => (typeof v === "number" ? v : null);
const rev = (i: ActivityItem) => (num(i.details.revision) !== null ? ` (r${num(i.details.revision)})` : "");
const plural = (n: number, one: string, many = `${one}s`) => `${n} ${n === 1 ? one : many}`;
const named = (i: ActivityItem, fallback: string) => {
  const name = str(i.details.design) || str(i.details.filename);
  return name ? `"${name}"` : fallback;
};

const DESCRIPTIONS: Record<string, Describer> = {
  "user.registered": () => "created their VIA account",
  "auth.login_succeeded": () => "signed in",
  "auth.login_failed": () => "had a failed sign-in attempt",
  "auth.logged_out": () => "signed out",
  "auth.session_revoked": () => "signed out a device",
  "auth.password_changed": () => "changed their password",
  "auth.password_reset_requested": () => "requested a password reset",
  "auth.password_reset_completed": () => "reset their password",
  "user.profile_updated": () => "updated their profile",
  "organization.created": (i) => `created the organization "${str(i.details.name)}"`,
  "project.created": () => "created the project",
  "project.updated": (i) => {
    const changes = (i.details.changes ?? {}) as Record<string, { to?: unknown } | boolean>;
    const parts: string[] = [];
    if (changes.name && typeof changes.name === "object") parts.push(`renamed it to "${str(changes.name.to)}"`);
    if (changes.description) parts.push("edited the description");
    if (changes.visibility && typeof changes.visibility === "object") parts.push(`made it ${str(changes.visibility.to)}`);
    return parts.length ? parts.join(", ") : "updated the project";
  },
  "project.archived": () => "archived the project",
  "project.unarchived": () => "restored the project from the archive",
  "project.deleted": (i) => `deleted the project "${str(i.details.name)}"`,
  "project.member_added": (i) => `added ${str(i.details.member) || "a member"} as ${str(i.details.role)}`,
  "project.member_updated": (i) => `changed a member's role to ${str(i.details.to)}`,
  "project.member_removed": (i) => (i.details.self ? "left the project" : "removed a member"),
  "design.uploaded": (i) => `uploaded ${named(i, "a board")}${rev(i)}`,
  "design.upload_rejected": (i) => `had an upload rejected${str(i.details.filename) ? ` ("${str(i.details.filename)}")` : ""}`,
  "design.parsed": (i) => {
    const parts = num(i.details.components);
    return `imported revision${rev(i)}${parts !== null ? `: ${plural(parts, "component")}` : ""}`;
  },
  "design.parse_failed": (i) => `could not import revision${rev(i)}${str(i.details.error_code) ? ` (${str(i.details.error_code)})` : ""}`,
  "design.updated": (i) => `updated the design ${named(i, "")}`.trim(),
  "design.deleted": (i) => `deleted the design ${named(i, "")}`.trim(),
  "analysis.requested": (i) => `started an analysis of ${named(i, "a design")}${rev(i)}`,
  "analysis.completed": (i) => {
    const n = num(i.details.findings);
    return `completed an analysis${rev(i)}${n !== null ? `: ${plural(n, "finding")}` : ""}`;
  },
  "analysis.failed": (i) => `had an analysis fail${str(i.details.error_code) ? ` (${str(i.details.error_code)})` : ""}`,
  "finding.reviewed": (i) => `marked a finding ${str(i.details.status) || "reviewed"}${str(i.details.rule) ? ` (${str(i.details.rule)})` : ""}`,
  "optimization.requested": () => "started an optimization run",
  "optimization.completed": (i) => {
    const n = num(i.details.candidates);
    return `completed an optimization run${n !== null ? `: ${plural(n, "candidate")}` : ""}`;
  },
  "optimization.candidate_decided": (i) => `${str(i.details.status) || "decided on"} an optimization candidate`,
  "change_set.created": (i) => {
    const n = num(i.details.changes);
    return `created a change set${n !== null ? ` with ${plural(n, "change")}` : ""}${rev(i)}`;
  },
  "change_set.apply_requested": (i) => `requested to apply ${str(i.details.title) ? `"${str(i.details.title)}"` : "a change set"}`,
  "change_set.applied": (i) => `applied a change set, creating revision${rev(i)}`,
  "change_set.failed": (i) => `had a change set fail${str(i.details.code) ? ` (${str(i.details.code)})` : ""}`,
  "change_set.rolled_back": (i) => `rolled back ${str(i.details.title) ? `"${str(i.details.title)}"` : "a change set"}`,
  "change_set.discarded": (i) => `discarded ${str(i.details.title) ? `"${str(i.details.title)}"` : "a change set"}`,
  "ai.explained": () => "requested an AI explanation (unverified suggestion)",
  "ai.reviewed": () => "requested an AI design review (unverified suggestion)",
};

export type ActivityKind = "account" | "project" | "design" | "analysis" | "change" | "ai";

/** Broad category, for icons and for hiding account events from engineering feeds. */
export function activityKind(item: ActivityItem): ActivityKind {
  const prefix = item.action.split(".")[0];
  switch (prefix) {
    case "user":
    case "auth":
    case "organization":
      return "account";
    case "design":
      return "design";
    case "analysis":
    case "finding":
    case "optimization":
      return "analysis";
    case "change_set":
      return "change";
    case "ai":
      return "ai";
    default:
      return "project";
  }
}

/** Failures get a danger tone in the feed. */
export function activityFailed(item: ActivityItem): boolean {
  return /\.(failed|parse_failed|upload_rejected|login_failed)$/.test(item.action);
}

export function describeActivity(item: ActivityItem): string {
  return DESCRIPTIONS[item.action]?.(item) ?? item.action;
}
