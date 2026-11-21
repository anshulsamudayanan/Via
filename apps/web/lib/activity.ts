import type { ActivityItem } from "@via/types";

type Describer = (item: ActivityItem) => string;

const str = (v: unknown) => (typeof v === "string" ? v : "");

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
};

export function describeActivity(item: ActivityItem): string {
  return DESCRIPTIONS[item.action]?.(item) ?? item.action;
}
