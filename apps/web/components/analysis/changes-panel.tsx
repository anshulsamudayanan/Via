"use client";

import type { ChangeSet, FindingBrief, RevisionComparison } from "@via/types";
import { Badge, Button, Card, CardHeader, CardTitle, EmptyState, ErrorState, Skeleton, Spinner } from "@via/ui";
import { Download, GitBranch, Trash2, Undo2, Upload } from "lucide-react";
import { useState } from "react";

import { usePolling } from "@/components/analysis/analysis-panel";
import { useApi } from "@/components/api-context";
import { errorMessage } from "@/lib/errors";
import { CHANGE_KIND_LABEL, describeChange, formatDelta, formatMetric, metricLabel, severityTone, SOURCE_LABEL } from "@/lib/findings";
import { formatBytes, formatDateTime } from "@/lib/format";
import { useAsync } from "@/lib/use-async";

const STATUS: Record<ChangeSet["status"], { label: string; tone: "neutral" | "accent" | "success" | "danger" | "warning" }> = {
  draft: { label: "Draft", tone: "neutral" },
  applying: { label: "Applying…", tone: "accent" },
  applied: { label: "Applied", tone: "success" },
  failed: { label: "Failed", tone: "danger" },
  rolled_back: { label: "Rolled back", tone: "warning" },
};

interface Props {
  designId: string;
  currentRevisionId: string | null;
  canEdit: boolean;
  /** The design's current revision changed (applied or rolled back). */
  onRevisionChanged: () => void;
}

export function ChangesPanel({ designId, currentRevisionId, canEdit, onRevisionChanged }: Props) {
  const client = useApi();
  const sets = useAsync((s) => client.changes.list(designId, s), [client, designId]);
  const applying = sets.data?.some((cs) => cs.status === "applying") ?? false;
  usePolling(applying, sets.reload);
  const [wasApplying, setWasApplying] = useState(false);
  if (applying !== wasApplying) {
    setWasApplying(applying);
    if (wasApplying && !applying) onRevisionChanged();
  }

  if (sets.error) return <ErrorState title="Couldn't load change sets" description={errorMessage(sets.error)} />;
  if (!sets.data) return <Skeleton className="h-40 w-full" />;
  return (
    <div className="space-y-4">
      <Card>
        <CardHeader>
          <div>
            <CardTitle>Changes</CardTitle>
            <p className="text-xs text-muted">
              Applying a change set edits only the changed objects in your original KiCad file, verifies the result by re-reading it, and adds it as a new revision. Rolling back makes the previous revision current again; nothing is deleted.
            </p>
          </div>
        </CardHeader>
        {sets.data.length === 0 ? (
          <EmptyState icon={<GitBranch />} title="No change sets yet" description="Accept optimization candidates, then create a change set from the Optimize tab." />
        ) : null}
      </Card>
      {sets.data.map((cs) => (
        <ChangeSetCard key={cs.id} cs={cs} designId={designId} currentRevisionId={currentRevisionId} canEdit={canEdit}
          onChanged={(revisionChanged) => { sets.reload(); if (revisionChanged) onRevisionChanged(); }} />
      ))}
    </div>
  );
}

function ChangeSetCard({ cs, designId, currentRevisionId, canEdit, onChanged }: {
  cs: ChangeSet; designId: string; currentRevisionId: string | null; canEdit: boolean; onChanged: (revisionChanged: boolean) => void;
}) {
  const client = useApi();
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [showPreview, setShowPreview] = useState(false);
  const editable = canEdit && (cs.status === "draft" || cs.status === "failed");

  async function act(fn: () => Promise<unknown>, revisionChanged = false) {
    setBusy(true);
    setError(null);
    try {
      await fn();
      onChanged(revisionChanged);
    } catch (err) {
      setError(errorMessage(err));
    } finally {
      setBusy(false);
    }
  }

  return (
    <Card aria-label={`Change set ${cs.title}`}>
      <CardHeader>
        <div className="min-w-0">
          <CardTitle className="flex flex-wrap items-center gap-2">
            <span className="break-words">{cs.title}</span>
            <Badge tone={STATUS[cs.status].tone}>{STATUS[cs.status].label}</Badge>
          </CardTitle>
          <p className="text-xs text-muted">
            {cs.changes.length} change{cs.changes.length === 1 ? "" : "s"} · created {formatDateTime(cs.created_at)}
            {cs.applied_at ? ` · applied ${formatDateTime(cs.applied_at)}` : ""}
            {cs.rolled_back_at ? ` · rolled back ${formatDateTime(cs.rolled_back_at)}` : ""}
          </p>
        </div>
        <div className="flex flex-wrap gap-1.5">
          {editable ? (
            <>
              <Button size="sm" variant="primary" disabled={busy} onClick={() => void act(() => client.changes.apply(cs.id))}><Upload /> Apply</Button>
              <Button size="sm" variant="ghost" aria-label="Discard change set" disabled={busy} onClick={() => void act(() => client.changes.discard(cs.id))}><Trash2 /></Button>
            </>
          ) : null}
          {cs.status === "applied" || cs.status === "rolled_back" ? (
            <Button asChild size="sm"><a href={client.changes.downloadUrl(cs.id)}><Download /> Download file</a></Button>
          ) : null}
          {canEdit && cs.status === "applied" && cs.result_revision_id === currentRevisionId ? (
            <Button size="sm" variant="ghost" disabled={busy} onClick={() => void act(() => client.changes.rollback(cs.id), true)}><Undo2 /> Roll back</Button>
          ) : null}
        </div>
      </CardHeader>
      <div className="space-y-3 px-4 pb-4 text-sm">
        {cs.status === "applying" ? <div role="status" className="flex items-center gap-2 text-muted"><Spinner label="" /> Patching, verifying and importing the new revision…</div> : null}
        {cs.error_message ? <ErrorState title="The change set couldn't be applied" description={`${cs.error_message} (${cs.error_code})`} /> : null}
        {error ? <ErrorState title={error} /> : null}
        <ul aria-label="Changes" className="divide-y divide-border rounded-md border border-border text-xs">
          {cs.changes.map((ch) => (
            <li key={ch.id} className="flex flex-wrap items-center gap-2 px-2 py-1">
              <span className="w-32 shrink-0">{CHANGE_KIND_LABEL[ch.kind] ?? ch.kind}</span>
              <span className="font-mono">{ch.target.label ?? ch.target.id}</span>
              <span className="text-muted">{describeChange(ch.kind, ch.before, ch.after)}</span>
              <Badge>{ch.source === "user" ? "entered by you" : "VIA Optimize"}</Badge>
              {ch.status === "refused" ? <span className="w-full text-danger">Refused: {ch.status_reason}</span> : null}
              {editable && cs.changes.length > 1 ? (
                <Button size="sm" variant="ghost" className="ml-auto h-6" disabled={busy} aria-label={`Remove change ${ch.ordinal + 1}`}
                  onClick={() => void act(() => client.changes.removeChange(cs.id, ch.id))}>Remove</Button>
              ) : null}
            </li>
          ))}
        </ul>
        {cs.status === "draft" || cs.status === "failed" ? (
          <button type="button" className="text-xs text-accent hover:underline" aria-expanded={showPreview} onClick={() => setShowPreview((p) => !p)}>
            {showPreview ? "Hide preview" : "Preview the effect"}
          </button>
        ) : null}
        {showPreview ? <Preview id={cs.id} /> : null}
        {cs.result.sha256 ? (
          <p className="text-xs text-muted">
            Exported {cs.result.size_bytes ? formatBytes(cs.result.size_bytes) : ""} · verified: {cs.result.verification} · SHA-256 <code className="break-all">{cs.result.sha256}</code>
          </p>
        ) : null}
        {cs.result_revision_id && (cs.status === "applied" || cs.status === "rolled_back") ? (
          <Comparison designId={designId} base={cs.base_revision_id} head={cs.result_revision_id} />
        ) : null}
      </div>
    </Card>
  );
}

function Preview({ id }: { id: string }) {
  const client = useApi();
  const preview = useAsync((s) => client.changes.preview(id, s), [client, id]);
  if (preview.error) return <ErrorState title="Couldn't compute the preview" description={errorMessage(preview.error)} />;
  if (!preview.data) return <Skeleton className="h-16" />;
  const p = preview.data;
  return (
    <div className="text-xs">
      <p className="mb-1 text-muted">Simulated on VIA&apos;s model of the board (not the exported file). Lower is better.</p>
      <dl className="grid grid-cols-2 gap-x-4 gap-y-0.5 sm:grid-cols-3">
        {Object.keys(p.before).map((k) => (
          <div key={k} className="flex justify-between gap-2">
            <dt className="text-muted">{metricLabel(k)}</dt>
            <dd className="font-mono">{formatMetric(k, p.after[k])} <span className="text-muted">({formatDelta(k, p.deltas[k])})</span></dd>
          </div>
        ))}
      </dl>
    </div>
  );
}

function Comparison({ designId, base, head }: { designId: string; base: string; head: string }) {
  const client = useApi();
  const cmp = useAsync((s) => client.changes.compare(designId, base, head, s), [client, designId, base, head]);
  if (cmp.error) return <ErrorState title="Couldn't compare the revisions" description={errorMessage(cmp.error)} />;
  if (!cmp.data) return <Skeleton className="h-16" />;
  return <ComparisonView cmp={cmp.data} />;
}

export function ComparisonView({ cmp }: { cmp: RevisionComparison }) {
  const f = cmp.findings;
  return (
    <div className="space-y-2 rounded-md border border-border p-3 text-xs" aria-label="Revision comparison">
      <h4 className="font-medium">Revision {cmp.base.revision_number} → {cmp.head.revision_number}</h4>
      {f ? (
        <>
          <p>
            Findings {f.base_total} → {f.head_total}: <span className="text-success">{f.resolved.length} resolved</span>,{" "}
            <span className={f.introduced.length ? "text-danger" : ""}>{f.introduced.length} introduced</span>, {f.persisting} unchanged.
          </p>
          {cmp.findings_note ? <p className="text-muted">{cmp.findings_note}</p> : null}
          <BriefList label="Introduced" items={f.introduced} />
          <BriefList label="Resolved" items={f.resolved} />
        </>
      ) : (
        <p className="text-muted">
          {cmp.head.analysis_run_id ? "" : "The new revision hasn't been analysed yet (an analysis is queued automatically when the base had one). "}
          {cmp.base.analysis_run_id ? "" : "The base revision has no analysis to compare against."}
        </p>
      )}
    </div>
  );
}

function BriefList({ label, items }: { label: string; items: FindingBrief[] }) {
  if (!items.length) return null;
  return (
    <div>
      <h5 className="font-medium">{label}</h5>
      <ul>
        {items.slice(0, 20).map((x) => (
          <li key={x.id} className="flex flex-wrap gap-1.5">
            <Badge tone={severityTone(x.severity)}>{x.severity}</Badge>
            {x.title}
            <span className="text-muted">({SOURCE_LABEL[x.source]})</span>
          </li>
        ))}
      </ul>
      {items.length > 20 ? <p className="text-muted">and {items.length - 20} more</p> : null}
    </div>
  );
}
