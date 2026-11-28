"use client";

import type { LearnEntry } from "@via/types";
import { Badge } from "@via/ui";
import type { ReactNode } from "react";

import { formatDateTime } from "@/lib/format";
import { CATEGORY_LABEL, LEARN_VERIFICATION_LABEL, STATUS_LABEL } from "@/lib/learn";

/** One entry with its attribution. Contributor identity is never in the payload, so it is not shown. */
export function EntryCard({ entry, actions, children }: { entry: LearnEntry; actions?: ReactNode; children?: ReactNode }) {
  const withdrawn = entry.status === "withdrawn";
  return (
    <li className="space-y-1.5 px-4 py-3 text-sm" id={`entry-${entry.id}`}>
      <div className="flex flex-wrap items-center gap-1.5">
        <Badge>{CATEGORY_LABEL[entry.category]}</Badge>
        <Badge tone={entry.verification_status === "unverified" ? "warning" : "success"}>{LEARN_VERIFICATION_LABEL[entry.verification_status]}</Badge>
        {entry.status !== "approved" ? <Badge tone={entry.status === "rejected" || withdrawn ? "neutral" : "accent"}>{STATUS_LABEL[entry.status]}</Badge> : null}
        {entry.mine ? <Badge>Yours</Badge> : null}
        <span className="font-medium">{withdrawn ? "Withdrawn by contributor" : entry.title}</span>
      </div>
      {withdrawn ? (
        <p className="text-xs text-muted">The content was erased on {entry.withdrawn_at ? formatDateTime(entry.withdrawn_at) : "withdrawal"}. The record of who owned it and where it came from is kept.</p>
      ) : (
        <p className="whitespace-pre-wrap">{entry.description}</p>
      )}
      <p className="text-xs text-muted">
        Source: {entry.source || "not stated"} · {entry.origin === "project_derived" ? "derived from a project, identifiers removed" : "written by a contributor"} · version {entry.version}
        {entry.verification_basis ? ` · basis: ${entry.verification_basis}` : ""}
      </p>
      {entry.review_note ? <p className="text-xs text-muted">Reviewer note: {entry.review_note}</p> : null}
      {children}
      {actions ? <div className="flex flex-wrap gap-1.5 pt-1">{actions}</div> : null}
    </li>
  );
}
