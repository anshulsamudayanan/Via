"use client";

import { ApiError } from "@via/api-client";
import type { AIOutput, AIStatus, AnalysisRun, Finding, FindingDetail, FindingFilters, FindingStatus, Recommendation } from "@via/types";
import { Badge, Button, Card, CardHeader, CardTitle, cn, EmptyState, ErrorState, Input, Select, Skeleton, Spinner, Textarea } from "@via/ui";
import { Bot, CheckCircle2, ShieldCheck, X } from "lucide-react";
import { useSearchParams } from "next/navigation";
import { useEffect, useState } from "react";

import { useApi } from "@/components/api-context";
import { errorMessage, rejectedProblems } from "@/lib/errors";
import { findingHighlight, SEVERITIES, severityTone, SOURCE_LABEL, VERIFICATION_LABEL } from "@/lib/findings";
import { formatDateTime } from "@/lib/format";
import type { Highlight } from "@/lib/pcb/overlay";
import { useAsync } from "@/lib/use-async";

const ACTIVE = new Set(["queued", "running"]);
const PAGE = 50;

interface Props {
  projectId: string;
  designId: string;
  revisionId: string;
  canEdit: boolean;
  onHighlight: (h: Highlight | null) => void;
}

/** Re-run `reload` every `ms` while `active`. */
export function usePolling(active: boolean, reload: () => void, ms = 2000) {
  useEffect(() => {
    if (!active) return;
    const t = window.setTimeout(reload, ms);
    return () => window.clearTimeout(t);
  });
}

export function AnalysisPanel({ projectId, designId, revisionId, canEdit, onHighlight }: Props) {
  const client = useApi();
  const runs = useAsync((s) => client.analysis.runs(designId, { limit: 20 }, s), [client, designId]);
  const ai = useAsync((s) => client.ai.status(s), [client]);
  const run = runs.data?.items.find((r) => r.revision_id === revisionId) ?? null;
  usePolling(Boolean(run && ACTIVE.has(run.status)), runs.reload);
  const [starting, setStarting] = useState(false);
  const [startError, setStartError] = useState<string | null>(null);

  async function start() {
    setStarting(true);
    setStartError(null);
    try {
      await client.analysis.start(designId, { revision_id: revisionId });
      runs.reload();
    } catch (err) {
      setStartError(errorMessage(err));
    } finally {
      setStarting(false);
    }
  }

  if (runs.error) return <ErrorState title="Couldn't load analyses" description={errorMessage(runs.error)} />;
  if (!runs.data) return <Skeleton className="h-40 w-full" />;

  return (
    <div className="space-y-4">
      <Card>
        <CardHeader>
          <div>
            <CardTitle>Analysis</CardTitle>
            <p className="text-xs text-muted">
              VIA&apos;s deterministic checks and KiCad&apos;s own DRC on this revision. Each finding says where it came from and how it was verified.
            </p>
          </div>
          {canEdit ? (
            <Button variant="primary" onClick={() => void start()} disabled={starting || Boolean(run && ACTIVE.has(run.status))}>
              {run ? "Run again" : "Run analysis"}
            </Button>
          ) : null}
        </CardHeader>
        {startError ? <ErrorState className="mx-4 mb-3" title={startError} /> : null}
        {run ? <RunSummary run={run} /> : (
          <EmptyState title="Not analysed yet" description={canEdit ? "Run an analysis to check this revision." : "An editor can run an analysis on this revision."} />
        )}
      </Card>
      {run?.status === "succeeded" ? (
        <Findings key={run.id} run={run} projectId={projectId} canEdit={canEdit} ai={ai.data ?? null} onHighlight={onHighlight} />
      ) : null}
      {run?.status === "succeeded" ? <Recommendations designId={designId} projectId={projectId} run={run} canEdit={canEdit} ai={ai.data ?? null} /> : null}
    </div>
  );
}

function RunSummary({ run }: { run: AnalysisRun }) {
  const [open, setOpen] = useState(false);
  if (ACTIVE.has(run.status)) {
    return (
      <div role="status" className="flex items-center gap-2 px-4 pb-4 text-sm text-muted">
        <Spinner label="" /> Analysis {run.status === "queued" ? "queued" : "running"}… this updates automatically.
      </div>
    );
  }
  if (run.status === "failed") {
    return <ErrorState className="mx-4 mb-4" title="The analysis failed" description={`${run.error_message ?? ""} (${run.error_code ?? "error"})`} />;
  }
  const by = run.summary.by_severity;
  const checks = run.summary.checks;
  return (
    <div className="space-y-2 px-4 pb-4 text-sm">
      <div className="flex flex-wrap items-center gap-2">
        <span className="font-medium">{run.summary.finding_count ?? 0} findings</span>
        {SEVERITIES.map((s) => (by?.[s] ? <Badge key={s} tone={severityTone(s)}>{by[s]} {s}</Badge> : null))}
        <span className="text-xs text-muted">
          {checks ? `${checks.ok} checks ran${checks.skipped ? `, ${checks.skipped} skipped` : ""}${checks.error ? `, ${checks.error} errored` : ""}` : ""}
          {run.finished_at ? ` · ${formatDateTime(run.finished_at)}` : ""} · analysis v{run.analysis_version}
        </span>
        <button type="button" className="text-xs text-accent hover:underline" onClick={() => setOpen((o) => !o)} aria-expanded={open}>
          {open ? "Hide checks" : "Show checks"}
        </button>
      </div>
      {open ? (
        <ul className="divide-y divide-border rounded-md border border-border text-xs">
          {run.checks.map((c) => (
            <li key={c.check_id} className="flex flex-wrap gap-2 px-3 py-1.5">
              <code className="w-48 shrink-0">{c.check_id}</code>
              <Badge tone={c.status === "ok" ? "success" : c.status === "error" ? "danger" : "neutral"}>{c.status}</Badge>
              <span className="text-muted">{c.finding_count} finding{c.finding_count === 1 ? "" : "s"}</span>
              {c.message ? <span className="w-full text-muted">{c.message}</span> : null}
            </li>
          ))}
        </ul>
      ) : null}
    </div>
  );
}

function Findings({ run, projectId, canEdit, ai, onHighlight }: { run: AnalysisRun; projectId: string; canEdit: boolean; ai: AIStatus | null; onHighlight: Props["onHighlight"] }) {
  const client = useApi();
  const [filters, setFilters] = useState<FindingFilters>({ status: "open" });
  const [offset, setOffset] = useState(0);
  const [query, setQuery] = useState("");
  const page = useAsync((s) => client.analysis.findings(run.id, { ...filters, limit: PAGE, offset }, s), [client, run.id, filters, offset]);
  // A finding linked from elsewhere (the Analysis page): ?finding=<id>.
  const linked = useSearchParams().get("finding");
  const [selected, setSelected] = useState<string | null>(linked);

  const set = (k: keyof FindingFilters, v: string) => {
    setOffset(0);
    setFilters((f) => ({ ...f, [k]: v || undefined }));
  };
  const pick = (f: Finding) => {
    setSelected(f.id);
    onHighlight(findingHighlight(f));
  };
  const facets = page.data?.facets;
  const option = (facet: "severity" | "status" | "category" | "source", value: string, label = value) => (
    <option key={value} value={value}>{label}{facets?.[facet]?.[value] !== undefined ? ` (${facets[facet][value]})` : ""}</option>
  );

  return (
    <div className="grid gap-4 lg:grid-cols-5">
      <Card className="min-w-0 lg:col-span-3">
        <div className="flex flex-wrap gap-2 border-b border-border p-3" role="group" aria-label="Filter findings">
          <Select className="w-auto" aria-label="Severity" value={filters.severity ?? ""} onChange={(e) => set("severity", e.target.value)}>
            <option value="">All severities</option>
            {SEVERITIES.map((s) => option("severity", s))}
          </Select>
          <Select className="w-auto" aria-label="Source" value={filters.source ?? ""} onChange={(e) => set("source", e.target.value)}>
            <option value="">All sources</option>
            {(Object.keys(SOURCE_LABEL) as (keyof typeof SOURCE_LABEL)[]).map((s) => option("source", s, SOURCE_LABEL[s]))}
          </Select>
          <Select className="w-auto" aria-label="Category" value={filters.category ?? ""} onChange={(e) => set("category", e.target.value)}>
            <option value="">All categories</option>
            {Object.keys(facets?.category ?? {}).sort().map((c) => option("category", c))}
          </Select>
          <Select className="w-auto" aria-label="Status" value={filters.status ?? ""} onChange={(e) => set("status", e.target.value)}>
            <option value="">Any status</option>
            {(["open", "reviewed", "dismissed"] as const).map((s) => option("status", s))}
          </Select>
          <form className="min-w-40 flex-1" onSubmit={(e) => { e.preventDefault(); set("q", query.trim()); }}>
            <Input aria-label="Search findings" placeholder="Title, part or net" value={query} onChange={(e) => setQuery(e.target.value)} />
          </form>
        </div>
        {page.error ? <ErrorState className="m-3" title="Couldn't load findings" description={errorMessage(page.error)} /> : null}
        {!page.data ? <Skeleton className="m-3 h-40" /> : page.data.items.length === 0 ? (
          <EmptyState icon={<CheckCircle2 />} title="No findings match" description="Change the filters to see other findings." />
        ) : (
          <ul aria-label="Findings" className="divide-y divide-border">
            {page.data.items.map((f) => (
              <li key={f.id}>
                <button
                  type="button"
                  onClick={() => pick(f)}
                  aria-current={selected === f.id ? "true" : undefined}
                  className={cn("flex w-full flex-col gap-1 px-3 py-2 text-left text-sm hover:bg-surface-hover", selected === f.id && "bg-accent-soft")}
                >
                  <span className="flex flex-wrap items-center gap-1.5">
                    <Badge tone={severityTone(f.severity)}>{f.severity}</Badge>
                    <span className="font-medium">{f.title}</span>
                  </span>
                  <span className="flex flex-wrap gap-2 text-xs text-muted">
                    <span>{SOURCE_LABEL[f.source]}</span>
                    <span>{f.category}</span>
                    {f.components.length ? <span>{f.components.slice(0, 4).join(", ")}{f.components.length > 4 ? "…" : ""}</span> : null}
                    {f.status !== "open" ? <span>· {f.status}</span> : null}
                  </span>
                </button>
              </li>
            ))}
          </ul>
        )}
        {page.data && page.data.total > PAGE ? (
          <div className="flex items-center justify-between border-t border-border px-3 py-2 text-xs text-muted">
            <span>{offset + 1}–{Math.min(offset + PAGE, page.data.total)} of {page.data.total}</span>
            <span className="flex gap-1">
              <Button size="sm" variant="ghost" disabled={offset === 0} onClick={() => setOffset(Math.max(0, offset - PAGE))}>Previous</Button>
              <Button size="sm" variant="ghost" disabled={offset + PAGE >= page.data.total} onClick={() => setOffset(offset + PAGE)}>Next</Button>
            </span>
          </div>
        ) : null}
      </Card>
      <div className="min-w-0 lg:col-span-2">
        {selected ? (
          <FindingPanel
            key={selected}
            findingId={selected}
            projectId={projectId}
            canEdit={canEdit}
            ai={ai}
            onClose={() => { setSelected(null); onHighlight(null); }}
            onReviewed={() => page.reload()}
          />
        ) : (
          <Card><EmptyState title="Select a finding" description="Its evidence appears here and its location is highlighted on the board." /></Card>
        )}
      </div>
    </div>
  );
}

function FindingPanel({ findingId, projectId, canEdit, ai, onClose, onReviewed }: {
  findingId: string; projectId: string; canEdit: boolean; ai: AIStatus | null; onClose: () => void; onReviewed: () => void;
}) {
  const client = useApi();
  const detail = useAsync((s) => client.analysis.finding(findingId, s), [client, findingId]);
  if (detail.error) return <ErrorState title="Couldn't load the finding" description={errorMessage(detail.error)} />;
  if (!detail.data) return <Skeleton className="h-64 w-full" />;
  const f = detail.data;
  return (
    <Card aria-label="Finding details">
      <CardHeader>
        <div className="min-w-0">
          <CardTitle className="break-words">{f.title}</CardTitle>
          <div className="mt-1 flex flex-wrap gap-1">
            <Badge tone={severityTone(f.severity)}>{f.severity}</Badge>
            <Badge>{SOURCE_LABEL[f.source]}</Badge>
            <Badge tone={f.verification === "verified" ? "success" : "neutral"}>{VERIFICATION_LABEL[f.verification]}</Badge>
            <Badge>confidence {Math.round(f.confidence * 100)}%</Badge>
          </div>
        </div>
        <Button size="icon" variant="ghost" aria-label="Close finding" onClick={onClose}><X /></Button>
      </CardHeader>
      <div className="space-y-3 px-4 pb-4 text-sm">
        <p>{f.description}</p>
        {f.explanation ? <p className="text-muted">{f.explanation}</p> : null}
        {f.evidence.length ? (
          <div>
            <h3 className="mb-1 text-xs font-medium">Evidence (measured)</h3>
            <dl className="divide-y divide-border rounded-md border border-border text-xs">
              {f.evidence.map((e, i) => (
                <div key={i} className="flex justify-between gap-3 px-2 py-1">
                  <dt className="text-muted">{e.label}</dt>
                  <dd className="text-right font-mono">{e.value}{e.expected ? <span className="text-muted"> (expected {e.expected})</span> : null}</dd>
                </div>
              ))}
            </dl>
          </div>
        ) : null}
        {f.suggested_resolution ? (
          <div>
            <h3 className="mb-1 text-xs font-medium">Suggested resolution</h3>
            <p className="text-muted">{f.suggested_resolution}</p>
          </div>
        ) : null}
        {f.components.length || f.nets.length ? (
          <p className="text-xs text-muted">
            {f.components.length ? <>Parts: {f.components.join(", ")}. </> : null}
            {f.nets.length ? <>Nets: {f.nets.join(", ")}.</> : null}
          </p>
        ) : null}
        <p className="text-xs text-muted">Check <code>{f.check_id}</code> v{f.check_version} · rule <code>{f.rule}</code></p>
        {canEdit ? <Review finding={f} onDone={(d) => { detail.setData(d); onReviewed(); }} /> : null}
        {f.history.length ? (
          <ul className="space-y-0.5 text-xs text-muted">
            {f.history.map((h, i) => (
              <li key={i}>{h.from_status} → {h.to_status}{h.reason ? `: ${h.reason}` : ""} · {h.actor?.display_name ?? "VIA"}{h.carried_over ? " (carried over)" : ""}</li>
            ))}
          </ul>
        ) : null}
        {ai?.enabled ? <Explain findingId={f.id} projectId={projectId} external={ai.external} /> : (
          <p className="text-xs text-muted">AI explanations are off: no AI provider is configured on this VIA server.</p>
        )}
      </div>
    </Card>
  );
}

function Review({ finding, onDone }: { finding: FindingDetail; onDone: (d: FindingDetail) => void }) {
  const client = useApi();
  const [reason, setReason] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  async function set(status: FindingStatus) {
    setBusy(true);
    setError(null);
    try {
      onDone(await client.analysis.review(finding.id, status, reason.trim() || undefined));
      setReason("");
    } catch (err) {
      setError(errorMessage(err));
    } finally {
      setBusy(false);
    }
  }
  return (
    <div className="space-y-2 rounded-md border border-border p-2">
      <Textarea aria-label="Review note" rows={2} placeholder="Note (required to dismiss)" value={reason} onChange={(e) => setReason(e.target.value)} />
      {error ? <p className="text-xs text-danger">{error}</p> : null}
      <div className="flex flex-wrap gap-1.5">
        {finding.status !== "reviewed" ? <Button size="sm" disabled={busy} onClick={() => void set("reviewed")}><ShieldCheck /> Mark reviewed</Button> : null}
        {finding.status !== "dismissed" ? <Button size="sm" variant="ghost" disabled={busy || !reason.trim()} onClick={() => void set("dismissed")}>Dismiss</Button> : null}
        {finding.status !== "open" ? <Button size="sm" variant="ghost" disabled={busy} onClick={() => void set("open")}>Reopen</Button> : null}
      </div>
    </div>
  );
}

/** AI output, always labelled as an unverified suggestion with VIA's grounding check next to it. */
export function AIAnswer({ output }: { output: AIOutput }) {
  const o = output.output;
  return (
    <div className="space-y-2 rounded-md border border-border bg-surface-raised p-3 text-sm" aria-label="AI suggestion">
      <div className="flex flex-wrap items-center gap-1.5 text-xs">
        <Badge tone="warning"><Bot className="size-3" /> AI suggestion · unverified</Badge>
        <Badge tone={output.grounding.ok ? "success" : "danger"}>{output.grounding.ok ? "Grounded in the design data" : "Grounding problems"}</Badge>
        <span className="text-muted">{output.model} · prompt {output.prompt_version}</span>
      </div>
      <p className="whitespace-pre-wrap">{o.answer}</p>
      {o.key_points?.length ? <ul className="list-disc pl-5 text-muted">{o.key_points.map((k, i) => <li key={i}>{k}</li>)}</ul> : null}
      {o.uncertainties?.length ? <p className="text-xs text-muted">Uncertain: {o.uncertainties.join(" ")}</p> : null}
    </div>
  );
}

function Problems({ list }: { list: string[] }) {
  if (!list.length) return null;
  return (
    <div className="space-y-1 text-xs text-muted">
      <p>What VIA&apos;s check found wrong with the answer:</p>
      <ul className="list-disc pl-5">{list.map((p, i) => <li key={i}>{p}</li>)}</ul>
    </div>
  );
}

function Explain({ findingId, projectId, external }: { findingId: string; projectId: string; external: boolean }) {
  const client = useApi();
  const [answer, setAnswer] = useState<AIOutput | null>(null);
  const [error, setError] = useState<ApiError | Error | null>(null);
  const [busy, setBusy] = useState(false);
  async function ask() {
    setBusy(true);
    setError(null);
    try {
      setAnswer(await client.ai.explainFinding(findingId));
    } catch (err) {
      setError(err instanceof Error ? err : new Error(String(err)));
    } finally {
      setBusy(false);
    }
  }
  const needsConsent = error instanceof ApiError && error.code === "consent_required";
  return (
    <div className="space-y-2">
      <Button size="sm" onClick={() => void ask()} disabled={busy}><Bot /> {busy ? "Asking…" : "Explain with AI"}</Button>
      {external ? <p className="text-xs text-muted">The AI provider is external: project data leaves VIA only with the project&apos;s consent.</p> : null}
      {error ? <p className="text-xs text-danger">{errorMessage(error)}</p> : null}
      <Problems list={rejectedProblems(error)} />
      {needsConsent ? (
        <Button size="sm" variant="ghost" onClick={() => void client.ai.grantConsent(projectId).then(() => ask(), (e: unknown) => setError(e as Error))}>
          Allow AI processing for this project
        </Button>
      ) : null}
      {answer ? <AIAnswer output={answer} /> : null}
    </div>
  );
}

function Recommendations({ designId, projectId, run, canEdit, ai }: { designId: string; projectId: string; run: AnalysisRun; canEdit: boolean; ai: AIStatus | null }) {
  const client = useApi();
  const recs = useAsync((s) => client.ai.recommendations(designId, undefined, s), [client, designId]);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [needsConsent, setNeedsConsent] = useState(false);
  const [problems, setProblems] = useState<string[]>([]);
  async function review() {
    setBusy(true);
    setError(null);
    setNeedsConsent(false);
    setProblems([]);
    try {
      await client.ai.review(designId, run.id);
      recs.reload();
    } catch (err) {
      setNeedsConsent(err instanceof ApiError && err.code === "consent_required");
      setProblems(rejectedProblems(err));
      setError(errorMessage(err));
    } finally {
      setBusy(false);
    }
  }
  async function decide(r: Recommendation, status: "accepted" | "rejected") {
    try {
      await client.ai.decideRecommendation(r.id, status);
      recs.reload();
    } catch (err) {
      setError(errorMessage(err));
    }
  }
  const items = recs.data ?? [];
  if (!ai?.enabled && !items.length) return null;
  return (
    <Card>
      <CardHeader>
        <div>
          <CardTitle>AI recommendations</CardTitle>
          <p className="text-xs text-muted">Suggestions from an AI design review. Unverified until you act on them and re-run the analysis.</p>
        </div>
        {canEdit && ai?.enabled ? <Button size="sm" onClick={() => void review()} disabled={busy}><Bot /> {busy ? "Reviewing…" : "AI design review"}</Button> : null}
      </CardHeader>
      {error ? <ErrorState className="mx-4 mb-3" title={error} /> : null}
      {problems.length ? <div className="mx-4 mb-3"><Problems list={problems} /></div> : null}
      {needsConsent ? (
        <div className="mx-4 mb-3">
          <Button size="sm" variant="ghost" onClick={() => void client.ai.grantConsent(projectId).then(() => review(), (e: unknown) => setError(errorMessage(e)))}>
            Allow AI processing for this project
          </Button>
        </div>
      ) : null}
      {items.length === 0 ? <EmptyState title="No recommendations yet" /> : (
        <ul className="divide-y divide-border text-sm">
          {items.map((r) => (
            <li key={r.id} className="space-y-1 px-4 py-2">
              <div className="flex flex-wrap items-center gap-1.5">
                <Badge tone="warning">AI suggestion</Badge>
                <Badge>{r.confidence} confidence</Badge>
                <Badge tone={r.status === "accepted" ? "success" : r.status === "rejected" ? "neutral" : "accent"}>{r.status}</Badge>
                <span className="font-medium">{r.problem}</span>
              </div>
              <p>{r.proposed_change}</p>
              <p className="text-xs text-muted">{r.rationale}</p>
              {r.required_validation.length ? <p className="text-xs text-muted">Validate: {r.required_validation.join("; ")}</p> : null}
              {canEdit && r.status === "open" ? (
                <div className="flex gap-1.5">
                  <Button size="sm" onClick={() => void decide(r, "accepted")}>Accept</Button>
                  <Button size="sm" variant="ghost" onClick={() => void decide(r, "rejected")}>Reject</Button>
                </div>
              ) : null}
            </li>
          ))}
        </ul>
      )}
    </Card>
  );
}
