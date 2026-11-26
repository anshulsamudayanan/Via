"use client";

import type { Candidate, CandidateDetail, Objective, OptimizationRun } from "@via/types";
import { Badge, Button, Card, CardHeader, CardTitle, EmptyState, ErrorState, Skeleton, Spinner, Table, TBody, TD, TH, THead, TR, Textarea } from "@via/ui";
import { GitPullRequestArrow, Play } from "lucide-react";
import { useState } from "react";

import { usePolling } from "@/components/analysis/analysis-panel";
import { useApi } from "@/components/api-context";
import { errorMessage } from "@/lib/errors";
import { CHANGE_KIND_LABEL, describeChange, formatDelta, formatMetric, metricLabel } from "@/lib/findings";
import type { Highlight } from "@/lib/pcb/overlay";
import { useAsync } from "@/lib/use-async";

export const OBJECTIVES: { id: Objective; label: string; hint: string }[] = [
  { id: "area", label: "Board area", hint: "Shrink the outline to fit the parts" },
  { id: "manufacturability", label: "Manufacturability", hint: "Fix widths and vias below the profile" },
  { id: "placement", label: "Placement", hint: "Shorten the ratsnest by moving unlocked parts" },
  { id: "routing", label: "Routing length", hint: "Shorter routed copper" },
  { id: "thermal", label: "Current capacity", hint: "Widen tracks for the currents you entered" },
  { id: "cost", label: "Relative cost", hint: "Illustrative index from area, layers and class" },
  { id: "layers", label: "Layer count", hint: "Propose fewer copper layers (manual)" },
];

const VALIDATION: Record<string, { label: string; tone: "success" | "danger" | "warning" | "neutral" }> = {
  passed: { label: "Validated", tone: "success" },
  failed: { label: "Failed validation", tone: "danger" },
  requires_rerouting: { label: "Needs re-routing", tone: "warning" },
  manual: { label: "Manual change", tone: "neutral" },
};

interface Props {
  designId: string;
  revisionId: string;
  canEdit: boolean;
  onHighlight: (h: Highlight | null) => void;
  /** Called after a change set was created from accepted candidates. */
  onChangeSetCreated: () => void;
}

export function OptimizePanel({ designId, revisionId, canEdit, onHighlight, onChangeSetCreated }: Props) {
  const client = useApi();
  const runs = useAsync((s) => client.optimization.runs(designId, s), [client, designId]);
  const run = runs.data?.find((r) => r.revision_id === revisionId) ?? null;
  usePolling(Boolean(run && (run.status === "queued" || run.status === "running")), runs.reload);
  const [objectives, setObjectives] = useState<Set<Objective>>(new Set(["area", "manufacturability"]));
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  async function start() {
    setBusy(true);
    setError(null);
    try {
      await client.optimization.start(designId, { objectives: [...objectives] });
      runs.reload();
    } catch (err) {
      setError(errorMessage(err));
    } finally {
      setBusy(false);
    }
  }
  const toggle = (o: Objective) =>
    setObjectives((prev) => {
      const next = new Set(prev);
      if (next.has(o)) next.delete(o);
      else next.add(o);
      return next;
    });

  if (runs.error) return <ErrorState title="Couldn't load optimization runs" description={errorMessage(runs.error)} />;
  if (!runs.data) return <Skeleton className="h-40 w-full" />;
  return (
    <div className="space-y-4">
      <Card>
        <CardHeader>
          <div>
            <CardTitle>Optimize</CardTitle>
            <p className="text-xs text-muted">
              VIA proposes explicit changes, measures them and re-runs its checks on the result. Nothing changes until you accept a candidate and apply it as a change set.
            </p>
          </div>
        </CardHeader>
        {canEdit ? (
          <div className="space-y-3 px-4 pb-4">
            <fieldset className="flex flex-wrap gap-x-4 gap-y-1.5">
              <legend className="mb-1 text-xs font-medium">Objectives</legend>
              {OBJECTIVES.map((o) => (
                <label key={o.id} className="flex items-center gap-1.5 text-sm" title={o.hint}>
                  <input type="checkbox" checked={objectives.has(o.id)} onChange={() => toggle(o.id)} />
                  {o.label}
                </label>
              ))}
            </fieldset>
            {error ? <ErrorState title={error} /> : null}
            <Button size="sm" variant="primary" disabled={busy || !objectives.size || Boolean(run && (run.status === "queued" || run.status === "running"))} onClick={() => void start()}>
              <Play /> Generate candidates
            </Button>
          </div>
        ) : null}
      </Card>
      {run ? <RunView key={run.id} run={run} canEdit={canEdit} designId={designId} onHighlight={onHighlight} onChangeSetCreated={onChangeSetCreated} /> : (
        <Card><EmptyState title="No optimization run for this revision" description={canEdit ? "Pick objectives and generate candidates." : "An editor can run the optimizer."} /></Card>
      )}
    </div>
  );
}

function RunView({ run, canEdit, designId, onHighlight, onChangeSetCreated }: { run: OptimizationRun; canEdit: boolean; designId: string } & Pick<Props, "onHighlight" | "onChangeSetCreated">) {
  const client = useApi();
  const candidates = useAsync((s) => (run.status === "succeeded" ? client.optimization.candidates(run.id, s) : Promise.resolve([] as Candidate[])), [client, run.id, run.status]);
  const [open, setOpen] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [creating, setCreating] = useState(false);

  if (run.status === "queued" || run.status === "running") {
    return <Card><div role="status" className="flex items-center gap-2 p-4 text-sm text-muted"><Spinner label="" /> Generating and validating candidates…</div></Card>;
  }
  if (run.status === "failed") return <ErrorState title="The optimization failed" description={`${run.error_message ?? ""} (${run.error_code ?? ""})`} />;
  if (candidates.error) return <ErrorState title="Couldn't load candidates" description={errorMessage(candidates.error)} />;
  if (!candidates.data) return <Skeleton className="h-40 w-full" />;
  const accepted = candidates.data.filter((c) => c.status === "accepted" && c.exportable_changes === c.change_count && c.change_count > 0);

  async function createChangeSet() {
    setCreating(true);
    setError(null);
    try {
      await client.changes.create(designId, { candidate_ids: accepted.map((c) => c.id), title: accepted.map((c) => c.title).join("; ").slice(0, 200) });
      onChangeSetCreated();
    } catch (err) {
      setError(errorMessage(err));
    } finally {
      setCreating(false);
    }
  }

  const notes = run.summary.notes ?? [];
  return (
    <Card>
      <CardHeader>
        <div>
          <CardTitle>Candidates ({candidates.data.length})</CardTitle>
          <p className="text-xs text-muted">Objectives: {(run.config.objectives ?? []).join(", ")} · optimizer v{run.optimizer_version}. Lower is better for every metric.</p>
        </div>
        {canEdit && accepted.length ? (
          <Button size="sm" variant="primary" disabled={creating} onClick={() => void createChangeSet()}>
            <GitPullRequestArrow /> Create change set ({accepted.length})
          </Button>
        ) : null}
      </CardHeader>
      {error ? <ErrorState className="mx-4 mb-3" title={error} /> : null}
      {notes.length ? <ul className="px-4 pb-2 text-xs text-muted">{notes.map((n, i) => <li key={i}>{n}</li>)}</ul> : null}
      {candidates.data.length === 0 ? <EmptyState title="No improvements found" description="VIA found nothing it could improve for these objectives." /> : (
        <ul className="divide-y divide-border">
          {candidates.data.map((c) => (
            <li key={c.id} className="px-4 py-2 text-sm">
              <button type="button" className="flex w-full flex-wrap items-center gap-1.5 text-left" aria-expanded={open === c.id} onClick={() => setOpen(open === c.id ? null : c.id)}>
                <Badge tone={VALIDATION[c.validation.status]?.tone ?? "neutral"}>{VALIDATION[c.validation.status]?.label ?? c.validation.status}</Badge>
                {c.pareto ? <Badge tone="accent">Pareto</Badge> : null}
                {c.status === "accepted" || c.status === "rejected" ? <Badge tone={c.status === "accepted" ? "success" : "neutral"}>{c.status}</Badge> : null}
                <span className="font-medium">{c.title}</span>
                <span className="text-xs text-muted">{c.change_count} change{c.change_count === 1 ? "" : "s"}</span>
              </button>
              <p className="mt-0.5 text-xs text-muted">{c.summary}</p>
              {open === c.id ? <CandidateView id={c.id} canEdit={canEdit} onHighlight={onHighlight} onDecided={() => candidates.reload()} /> : null}
            </li>
          ))}
        </ul>
      )}
    </Card>
  );
}

function delta(before: number | null | undefined, after: number | null | undefined): number | null {
  return before === null || before === undefined || after === null || after === undefined ? null : after - before;
}

function CandidateView({ id, canEdit, onHighlight, onDecided }: { id: string; canEdit: boolean; onHighlight: Props["onHighlight"]; onDecided: () => void }) {
  const client = useApi();
  const detail = useAsync((s) => client.optimization.candidate(id, s), [client, id]);
  const [reason, setReason] = useState("");
  const [error, setError] = useState<string | null>(null);
  if (detail.error) return <ErrorState title="Couldn't load the candidate" description={errorMessage(detail.error)} />;
  if (!detail.data) return <Skeleton className="mt-2 h-24" />;
  const c: CandidateDetail = detail.data;
  const keys = Object.keys(c.metrics_before).filter((k) => c.metrics_before[k] !== c.metrics_after[k]);

  async function decide(status: "accepted" | "rejected") {
    setError(null);
    try {
      detail.setData(await client.optimization.decide(c.id, status, reason.trim() || undefined));
      onDecided();
    } catch (err) {
      setError(errorMessage(err));
    }
  }
  const refs = c.changes.filter((ch) => ch.target.kind === "component").map((ch) => ch.target.label ?? ch.target.id);

  return (
    <div className="mt-2 space-y-3 rounded-md border border-border p-3">
      {keys.length ? (
        <Table>
          <THead><TR><TH>Metric</TH><TH>Before</TH><TH>After</TH><TH>Change</TH></TR></THead>
          <TBody>
            {keys.map((k) => (
              <TR key={k}>
                <TD>{metricLabel(k)}</TD>
                <TD className="font-mono">{formatMetric(k, c.metrics_before[k])}</TD>
                <TD className="font-mono">{formatMetric(k, c.metrics_after[k])}</TD>
                <TD className="font-mono">{formatDelta(k, delta(c.metrics_before[k], c.metrics_after[k]))}</TD>
              </TR>
            ))}
          </TBody>
        </Table>
      ) : null}
      <div className="grid gap-2 text-xs sm:grid-cols-2">
        {c.expected_benefits.length ? <div><h4 className="font-medium">Benefits</h4><ul className="list-disc pl-4 text-muted">{c.expected_benefits.map((b, i) => <li key={i}>{b}</li>)}</ul></div> : null}
        {c.trade_offs.length ? <div><h4 className="font-medium">Trade-offs</h4><ul className="list-disc pl-4 text-muted">{c.trade_offs.map((b, i) => <li key={i}>{b}</li>)}</ul></div> : null}
      </div>
      {c.validation.new_problems.length || c.validation.notes.length ? (
        <div className="text-xs text-muted">
          {c.validation.new_problems.map((p, i) => <p key={i} className="text-danger">New problem: {p}</p>)}
          {c.validation.notes.map((n, i) => <p key={i}>{n}</p>)}
        </div>
      ) : null}
      <details>
        <summary className="cursor-pointer text-xs text-accent">Changes ({c.changes.length})</summary>
        <ul className="mt-1 max-h-48 overflow-auto text-xs">
          {c.changes.map((ch) => (
            <li key={ch.id} className="flex flex-wrap gap-2 py-0.5">
              <span className="w-32 shrink-0">{CHANGE_KIND_LABEL[ch.kind] ?? ch.kind}</span>
              <span className="font-mono">{ch.target.label ?? ch.target.id}</span>
              <span className="text-muted">{describeChange(ch.kind, ch.before, ch.after)}</span>
              {!ch.exportable ? <Badge>manual</Badge> : null}
            </li>
          ))}
        </ul>
      </details>
      {refs.length ? <Button size="sm" variant="ghost" onClick={() => onHighlight({ references: refs, nets: [], regions: [], focus: true })}>Show parts on the board</Button> : null}
      {canEdit && c.status !== "accepted" && c.status !== "rejected" ? (
        <div className="space-y-2">
          <Textarea aria-label="Decision note" rows={2} placeholder="Note (required to reject)" value={reason} onChange={(e) => setReason(e.target.value)} />
          {error ? <p className="text-xs text-danger">{error}</p> : null}
          <div className="flex gap-1.5">
            <Button size="sm" variant="primary" disabled={c.status !== "validated"} title={c.status !== "validated" ? "Only validated candidates can be accepted" : undefined} onClick={() => void decide("accepted")}>Accept</Button>
            <Button size="sm" variant="ghost" disabled={!reason.trim()} onClick={() => void decide("rejected")}>Reject</Button>
          </div>
        </div>
      ) : null}
    </div>
  );
}
