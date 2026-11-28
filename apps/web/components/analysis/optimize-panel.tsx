"use client";

import type { Candidate, CandidateDetail, CandidateLifecycle, ConstraintResult, Objective, OptimizationRun } from "@via/types";
import { Badge, Button, buttonVariants, Card, CardHeader, CardTitle, EmptyState, ErrorState, Skeleton, Spinner, Table, TBody, TD, TH, THead, TR, Textarea } from "@via/ui";
import { FileText, GitPullRequestArrow, Play } from "lucide-react";
import { useState } from "react";

import { usePolling } from "@/components/analysis/analysis-panel";
import { buildQuantityBody, ConstraintsForm, type ConstraintsInput, constraintsBody, DEFAULT_CONSTRAINTS, PricingForm, WeightsForm, weightsBody } from "@/components/analysis/optimize-options";
import { AnalysisCards, ComparisonTable } from "@/components/analysis/optimize-results";
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

type Tone = "success" | "danger" | "warning" | "neutral";

/** What the engineer sees for a candidate's lifecycle. "Passed VIA checks" is deliberately not "verified". */
const LIFECYCLE: Record<CandidateLifecycle, { label: string; tone: Tone; hint: string }> = {
  validated: { label: "Passed VIA checks", tone: "success", hint: "VIA re-ran its own checks and the listed constraints on the modified design and found no new problem. This is not a KiCad DRC or electrical verification." },
  validation_failed: { label: "Failed validation", tone: "danger", hint: "A hard constraint was violated or the change introduced a new problem." },
  needs_review: { label: "Needs review", tone: "warning", hint: "VIA can't fully verify this candidate: it needs re-routing, includes a manual change, or has a requirement VIA can't evaluate." },
  accepted: { label: "accepted", tone: "success", hint: "You accepted it. Create a change set to apply it as a new revision." },
  applied: { label: "applied", tone: "success", hint: "Applied as a new revision." },
  rejected: { label: "rejected", tone: "neutral", hint: "Rejected with a reason." },
};

const OBJECTIVE_LABEL: Record<string, string> = Object.fromEntries(OBJECTIVES.map((o) => [o.id, o.label]));

const CONSTRAINT_TONE: Record<ConstraintResult["status"], Tone> = { satisfied: "success", violated: "danger", unverified: "warning", not_applicable: "neutral" };

interface Props {
  projectId: string;
  /** Only the project owner can allow supplier lookups. */
  isOwner: boolean;
  designId: string;
  revisionId: string;
  canEdit: boolean;
  onHighlight: (h: Highlight | null) => void;
  /** Called after a change set was created from accepted candidates. */
  onChangeSetCreated: () => void;
}

export function OptimizePanel({ projectId, isOwner, designId, revisionId, canEdit, onHighlight, onChangeSetCreated }: Props) {
  const client = useApi();
  const runs = useAsync((s) => client.optimization.runs(designId, s), [client, designId]);
  const run = runs.data?.find((r) => r.revision_id === revisionId) ?? null;
  usePolling(Boolean(run && (run.status === "queued" || run.status === "running")), runs.reload);
  const [objectives, setObjectives] = useState<Set<Objective>>(new Set(["area", "manufacturability"]));
  const [constraints, setConstraints] = useState<ConstraintsInput>(DEFAULT_CONSTRAINTS);
  const [weights, setWeights] = useState<Partial<Record<Objective, string>>>({});
  const [quantity, setQuantity] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  async function start() {
    setError(null);
    const c = constraintsBody(constraints);
    const w = weightsBody(weights, objectives);
    const q = objectives.has("cost") ? buildQuantityBody(quantity) : ({ ok: true, value: undefined } as const);
    const bad = [c, w, q].find((r) => !r.ok);
    if (bad && !bad.ok) return setError(bad.error);
    setBusy(true);
    try {
      await client.optimization.start(designId, {
        objectives: [...objectives],
        constraints: c.ok ? c.value : undefined,
        weights: w.ok ? w.value : undefined,
        build_quantity: q.ok ? q.value : undefined,
      });
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
            <ConstraintsForm value={constraints} onChange={setConstraints} />
            <WeightsForm objectives={[...objectives]} labels={OBJECTIVE_LABEL} value={weights} onChange={setWeights} />
            {objectives.has("cost") ? <PricingForm projectId={projectId} isOwner={isOwner} value={quantity} onChange={setQuantity} /> : null}
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
    return (
      <Card>
        <div role="status" className="flex items-center gap-2 p-4 text-sm text-muted">
          <Spinner label="" /> {run.summary.phase ? `${run.summary.phase}…` : "Queued…"} <span className="text-xs text-subtle">VIA can&apos;t tell in advance how long this takes, so there is no percentage.</span>
        </div>
      </Card>
    );
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
  const changeCount = accepted.reduce((n, c) => n + c.change_count, 0);
  return (
    <>
    <AnalysisCards run={run} />
    <Card>
      <CardHeader>
        <div>
          <CardTitle>Candidates ({candidates.data.length})</CardTitle>
          <p className="text-xs text-muted">Objectives: {(run.config.objectives ?? []).join(", ")} · optimizer v{run.optimizer_version}. Lower is better for every metric.</p>
        </div>
        <div className="flex flex-wrap items-center gap-1.5">
          <a href={client.optimization.reportUrl(run.id)} download className={buttonVariants({ size: "sm", variant: "ghost" })}><FileText /> Report</a>
          {canEdit && accepted.length ? (
            <Button size="sm" variant="primary" disabled={creating} title={`Creates a draft change set with ${changeCount} change${changeCount === 1 ? "" : "s"}; nothing is applied until you apply it there.`} onClick={() => void createChangeSet()}>
              <GitPullRequestArrow /> Create change set ({accepted.length})
            </Button>
          ) : null}
        </div>
      </CardHeader>
      {candidates.data.length ? <ComparisonTable run={run} candidates={candidates.data} /> : null}
      {error ? <ErrorState className="mx-4 mb-3" title={error} /> : null}
      {notes.length ? <ul className="px-4 pb-2 text-xs text-muted">{notes.map((n, i) => <li key={i}>{n}</li>)}</ul> : null}
      {candidates.data.length === 0 ? <EmptyState title="No improvements found" description="VIA found nothing it could improve for these objectives." /> : (
        <ul className="divide-y divide-border">
          {candidates.data.map((c) => (
            <li key={c.id} className="px-4 py-2 text-sm">
              <button type="button" className="flex w-full flex-wrap items-center gap-1.5 text-left" aria-expanded={open === c.id} onClick={() => setOpen(open === c.id ? null : c.id)}>
                <Badge tone={LIFECYCLE[c.lifecycle]?.tone ?? "neutral"} title={LIFECYCLE[c.lifecycle]?.hint}>{LIFECYCLE[c.lifecycle]?.label ?? c.lifecycle}</Badge>
                {c.validation.status === "requires_rerouting" ? <Badge tone="warning" title="Moves parts that carry routed nets: re-route them in KiCad before connectivity can be verified">Needs re-routing</Badge> : null}
                {c.pareto ? <Badge tone="accent">Pareto</Badge> : null}
                {c.score?.rank ? <Badge tone="neutral" title="Preference order from your weights. It never changes validation.">Preference #{c.score.rank}</Badge> : null}
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
    </>
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
      <ConstraintList constraints={c.constraints_evaluated} />
      {c.limitations.length ? <div className="text-xs"><h4 className="font-medium">Limitations</h4><ul className="list-disc pl-4 text-muted">{c.limitations.map((l, i) => <li key={i}>{l}</li>)}</ul></div> : null}
      <details>
        <summary className="cursor-pointer text-xs text-accent">How it was produced</summary>
        <dl className="mt-1 space-y-0.5 text-xs text-muted">
          <div>Algorithm: <span className="font-mono">{c.algorithm} {c.algorithm_version}</span></div>
          <div>Candidate hash: <span className="font-mono">{c.candidate_hash.slice(0, 16)}</span> (the same inputs give the same hash)</div>
          {Object.entries(c.execution).map(([k, v]) => <div key={k}>{k.replace(/_/g, " ")}: <span className="font-mono">{String(v)}</span></div>)}
          {c.score ? <div>Preference score: <span className="font-mono">{c.score.value ?? "n/a"}</span>{c.score.partial ? ` (partial: ${c.score.excluded.join("; ")})` : ""}</div> : null}
        </dl>
      </details>
      {c.applied_revision ? <p className="text-xs text-success">Applied as revision {c.applied_revision.revision_number ?? "?"}.</p> : null}
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
            <Button size="sm" variant="primary" disabled={c.status !== "validated"} title={c.status !== "validated" ? "Only candidates that passed VIA's checks can be accepted" : undefined} onClick={() => void decide("accepted")}>Accept</Button>
            <Button size="sm" variant="ghost" disabled={!reason.trim()} onClick={() => void decide("rejected")}>Reject</Button>
          </div>
        </div>
      ) : null}
    </div>
  );
}

function ConstraintList({ constraints }: { constraints: ConstraintResult[] }) {
  if (!constraints.length) return <p className="text-xs text-muted">No constraints were evaluated: this change can&apos;t be applied automatically.</p>;
  const order: ConstraintResult["status"][] = ["violated", "unverified", "satisfied", "not_applicable"];
  const label: Record<ConstraintResult["status"], string> = { violated: "Violated", unverified: "Not verified", satisfied: "Satisfied", not_applicable: "Not affected" };
  return (
    <div className="space-y-1 text-xs">
      <h4 className="font-medium">Constraints checked</h4>
      {order.map((status) => {
        const rows = constraints.filter((r) => r.status === status);
        if (!rows.length) return null;
        return (
          <div key={status} className="flex flex-wrap items-baseline gap-1.5">
            <Badge tone={CONSTRAINT_TONE[status]}>{label[status]} ({rows.length})</Badge>
            {rows.map((r) => <span key={r.id} className="font-mono text-muted" title={r.detail || undefined}>{r.id}</span>)}
          </div>
        );
      })}
      {constraints.filter((r) => r.status === "violated" || r.status === "unverified").map((r) => <p key={r.id} className={r.status === "violated" ? "text-danger" : "text-muted"}>{r.id}: {r.detail}</p>)}
    </div>
  );
}
