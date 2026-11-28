"use client";

import type { Evaluation, EvaluationTally, LearnCategory, LearnEntry, LearnVerification } from "@via/types";
import { Badge, Button, cn, EmptyState, ErrorState, Input, Panel, Select, Skeleton, Table, TBody, TD, TH, THead, Textarea, TR } from "@via/ui";
import { Search } from "lucide-react";
import { useEffect, useState } from "react";

import { useApi } from "@/components/api-context";
import { PageHeader } from "@/components/app-shell";
import { useSession } from "@/components/session";
import { errorMessage } from "@/lib/errors";
import { formatDateTime } from "@/lib/format";
import { CATEGORY_LABEL, FEEDBACK_LABEL, LEARN_VERIFICATION_LABEL, pct } from "@/lib/learn";
import { useAsync } from "@/lib/use-async";
import { pick, useUrlParams } from "@/lib/use-url-params";

import { EntryCard } from "./entry-card";

const VIEWS = ["library", "contributions", "review", "insights", "feedback"] as const;
const VIEW_LABEL: Record<(typeof VIEWS)[number], string> = {
  library: "Knowledge library",
  contributions: "My contributions",
  review: "Contribution review",
  insights: "Engineering insights",
  feedback: "Feedback history",
};
const PAGE = 25;

function Loading() {
  return (
    <div className="space-y-2 p-4">
      {Array.from({ length: 4 }, (_, i) => (
        <Skeleton key={i} className="h-10 w-full" />
      ))}
    </div>
  );
}

function Failed({ what, error, onRetry }: { what: string; error: unknown; onRetry: () => void }) {
  return (
    <ErrorState className="m-4" title={`Couldn't load ${what}`} description={errorMessage(error)} action={<Button size="sm" onClick={onRetry}>Retry</Button>} />
  );
}

// ------------------------------------------------------------------------------ library

function Library() {
  const client = useApi();
  const meta = useAsync((s) => client.learn.meta(s), [client]);
  const { params, update } = useUrlParams();
  const category = (params.get("category") ?? "") as LearnCategory | "";
  const verification = (params.get("verification") ?? "") as LearnVerification | "";
  const q = params.get("q") ?? "";
  const [search, setSearch] = useState(q);
  useEffect(() => {
    if (search === q) return;
    const id = window.setTimeout(() => update({ q: search.trim() || null }), 250);
    return () => window.clearTimeout(id);
  }, [search, q, update]);
  const result = useAsync(
    (s) => client.learn.search({ q: q || undefined, category: category || undefined, verification: verification || undefined, limit: PAGE }, s),
    [client, q, category, verification],
  );
  const entryId = params.get("entry");
  const linked = useAsync((s) => (entryId ? client.learn.entry(entryId, s) : Promise.resolve(null)), [client, entryId]);
  return (
    <>
      {entryId ? (
        <Panel className="mb-3">
          {linked.error ? (
            <p className="px-4 py-3 text-sm text-muted">That entry is no longer available. It may have been withdrawn.</p>
          ) : !linked.data ? <Loading /> : (
            <ul><EntryCard entry={linked.data} /></ul>
          )}
        </Panel>
      ) : null}
      <div className="mb-3 flex flex-wrap items-center gap-2">
        <div className="relative">
          <Search className="pointer-events-none absolute left-2 top-2 size-4 text-subtle" aria-hidden />
          <Input aria-label="Search the library" className="w-64 pl-8" placeholder="Search knowledge" value={search} onChange={(e) => setSearch(e.target.value)} />
        </div>
        <Select aria-label="Category" className="w-auto" value={category} onChange={(e) => update({ category: e.target.value || null })}>
          <option value="">All categories</option>
          {(meta.data?.categories ?? []).map((c) => (
            <option key={c} value={c}>{CATEGORY_LABEL[c]}</option>
          ))}
        </Select>
        <Select aria-label="Verification" className="w-auto" value={verification} onChange={(e) => update({ verification: e.target.value || null })}>
          <option value="">Any verification</option>
          {(["verified", "reviewed", "unverified"] as const).map((v) => (
            <option key={v} value={v}>{LEARN_VERIFICATION_LABEL[v]}</option>
          ))}
        </Select>
      </div>
      {meta.data ? <p className="mb-3 text-xs text-muted">{meta.data.retrieval.note}</p> : null}
      <Panel>
        {result.error ? <Failed what="the library" error={result.error} onRetry={result.reload} /> : !result.data ? <Loading /> : result.data.items.length === 0 ? (
          <EmptyState title={q ? "No matching knowledge" : "The library is empty"} description="Only approved contributions appear here. Nothing is added automatically." />
        ) : (
          <ul className="divide-y divide-border">
            {result.data.items.map((e) => (
              <EntryCard key={e.id} entry={e} />
            ))}
          </ul>
        )}
      </Panel>
      {result.data && result.data.total > result.data.items.length ? (
        <p className="mt-2 text-xs text-muted">Showing the best {result.data.items.length} of {result.data.total}. Narrow the search to see others.</p>
      ) : null}
    </>
  );
}

// ------------------------------------------------------------------------------ contributions

function NewContribution({ onCreated }: { onCreated: () => void }) {
  const client = useApi();
  const meta = useAsync((s) => client.learn.meta(s), [client]);
  const [category, setCategory] = useState<LearnCategory>("pcb_design_pattern");
  const [title, setTitle] = useState("");
  const [description, setDescription] = useState("");
  const [source, setSource] = useState("");
  const [rights, setRights] = useState(false);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const valid = title.trim().length >= 5 && description.trim().length >= 20 && source.trim().length >= 3 && rights;
  async function save() {
    setBusy(true);
    setError(null);
    try {
      await client.learn.contribute({ category, title: title.trim(), description: description.trim(), source: source.trim(), confirm_rights: rights });
      setTitle("");
      setDescription("");
      setSource("");
      setRights(false);
      onCreated();
    } catch (err) {
      setError(errorMessage(err));
    } finally {
      setBusy(false);
    }
  }
  return (
    <Panel className="mb-4 space-y-2 p-4">
      <h2 className="text-sm font-medium">Write a contribution</h2>
      <p className="text-xs text-muted">It stays a private draft until you review and submit it. Don&apos;t paste anything from a private design.</p>
      <Select aria-label="Contribution category" value={category} onChange={(e) => setCategory(e.target.value as LearnCategory)}>
        {(meta.data?.categories ?? [category]).map((c) => (
          <option key={c} value={c}>{CATEGORY_LABEL[c]}</option>
        ))}
      </Select>
      <Input aria-label="Title" placeholder="Title" value={title} maxLength={200} onChange={(e) => setTitle(e.target.value)} />
      <Textarea aria-label="Description" placeholder="What is the knowledge, and when does it apply?" value={description} maxLength={6000} onChange={(e) => setDescription(e.target.value)} />
      <Input aria-label="Source" placeholder="Source (a datasheet, standard, your own experience…)" value={source} maxLength={1000} onChange={(e) => setSource(e.target.value)} />
      <label className="flex items-start gap-2 text-xs text-muted">
        <input type="checkbox" className="mt-0.5 size-3.5 accent-accent" checked={rights} onChange={(e) => setRights(e.target.checked)} />
        This text is mine to share and contains nothing from a private design or anyone else&apos;s work.
      </label>
      {error ? <p role="alert" className="text-xs text-danger">{error}</p> : null}
      <Button size="sm" disabled={!valid || busy} onClick={() => void save()}>Save draft</Button>
    </Panel>
  );
}

function ProjectConsent() {
  const client = useApi();
  const projects = useAsync((s) => client.projects.list({ status: "active", sort: "name", limit: 100 }, s), [client]);
  const owned = (projects.data?.items ?? []).filter((p) => p.my_role === "owner");
  const [projectId, setProjectId] = useState("");
  const id = projectId || owned[0]?.id || "";
  const consent = useAsync((s) => (id ? client.learn.consent(id, s) : Promise.resolve(null)), [client, id]);
  const [error, setError] = useState<string | null>(null);
  const [note, setNote] = useState<string | null>(null);
  if (!owned.length) return null;
  async function act(fn: () => Promise<unknown>) {
    setError(null);
    setNote(null);
    try {
      await fn();
      consent.reload();
    } catch (err) {
      setError(errorMessage(err));
    }
  }
  const granted = consent.data?.granted ?? false;
  return (
    <Panel className="mb-4 space-y-2 p-4">
      <h2 className="text-sm font-medium">Project contributions to VIA Learn</h2>
      <p className="text-xs text-muted">
        Off by default. When you allow it, you can turn a recommendation from this project into a draft with part references, net names and design names removed. You still review and submit each one yourself. This is separate from AI processing and supplier pricing.
      </p>
      <div className="flex flex-wrap items-center gap-2">
        <Select aria-label="Project" className="w-auto max-w-56" value={id} onChange={(e) => setProjectId(e.target.value)}>
          {owned.map((p) => (
            <option key={p.id} value={p.id}>{p.name}</option>
          ))}
        </Select>
        <Badge tone={granted ? "accent" : "neutral"}>{granted ? "Allowed" : "Not allowed"}</Badge>
        {granted ? (
          <>
            <Button size="sm" variant="ghost" onClick={() => void act(async () => { const r = await client.learn.revokeConsent(id, false); setNote(`Consent withdrawn. Existing contributions stay. ${r.withdrawn_entries} withdrawn.`); })}>Stop allowing</Button>
            <Button size="sm" variant="ghost" onClick={() => void act(async () => { const r = await client.learn.revokeConsent(id, true); setNote(`Consent withdrawn and ${r.withdrawn_entries} contribution(s) withdrawn.`); })}>Stop and withdraw existing</Button>
          </>
        ) : (
          <Button size="sm" onClick={() => void act(() => client.learn.grantConsent(id))}>Allow contributions</Button>
        )}
      </div>
      {note ? <p role="status" className="text-xs text-muted">{note}</p> : null}
      {error ? <p role="alert" className="text-xs text-danger">{error}</p> : null}
    </Panel>
  );
}

function Contributions() {
  const client = useApi();
  const result = useAsync((s) => client.learn.contributions({ limit: 100 }, s), [client]);
  const [error, setError] = useState<string | null>(null);
  async function act(fn: () => Promise<unknown>) {
    setError(null);
    try {
      await fn();
      result.reload();
    } catch (err) {
      setError(errorMessage(err));
    }
  }
  function actions(e: LearnEntry) {
    if (e.status === "draft")
      return (
        <>
          <Button size="sm" onClick={() => void act(() => client.learn.submit(e.id))}>Submit for review</Button>
          <Button size="sm" variant="ghost" onClick={() => void act(() => client.learn.deleteDraft(e.id))}>Delete draft</Button>
        </>
      );
    if (e.status === "pending_review" || e.status === "approved")
      return <Button size="sm" variant="ghost" onClick={() => void act(() => client.learn.withdraw(e.id))}>Withdraw</Button>;
    return null;
  }
  return (
    <>
      <ProjectConsent />
      <NewContribution onCreated={result.reload} />
      {error ? <ErrorState className="mb-3" title={error} /> : null}
      <Panel>
        {result.error ? <Failed what="your contributions" error={result.error} onRetry={result.reload} /> : !result.data ? <Loading /> : result.data.items.length === 0 ? (
          <EmptyState title="No contributions yet" description="You decide what to share. Nothing from your projects is collected automatically." />
        ) : (
          <ul className="divide-y divide-border">
            {result.data.items.map((e) => (
              <EntryCard key={e.id} entry={e} actions={actions(e)}>
                {e.status === "approved" && e.permissions ? (
                  <div className="flex flex-wrap gap-3 text-xs text-muted">
                    <label className="flex items-center gap-1.5">
                      <input type="checkbox" className="size-3.5 accent-accent" checked={e.permissions.library_visible !== false} onChange={(ev) => void act(() => client.learn.setPermissions(e.id, { library_visible: ev.target.checked }))} />
                      Show in the library
                    </label>
                    <label className="flex items-center gap-1.5">
                      <input type="checkbox" className="size-3.5 accent-accent" checked={e.permissions.ai_retrieval !== false} onChange={(ev) => void act(() => client.learn.setPermissions(e.id, { ai_retrieval: ev.target.checked }))} />
                      Let VIA&apos;s AI use it as context
                    </label>
                  </div>
                ) : null}
              </EntryCard>
            ))}
          </ul>
        )}
      </Panel>
    </>
  );
}

// ------------------------------------------------------------------------------ review

function ReviewItem({ entry, onDone }: { entry: LearnEntry; onDone: () => void }) {
  const client = useApi();
  const [note, setNote] = useState("");
  const [level, setLevel] = useState<LearnVerification>("unverified");
  const [basis, setBasis] = useState("");
  const [error, setError] = useState<string | null>(null);
  async function decide(decision: "approve" | "reject") {
    setError(null);
    try {
      await client.learn.review(entry.id, {
        decision, note: note.trim() || undefined,
        verification_status: decision === "approve" ? level : undefined, verification_basis: basis.trim() || undefined,
      });
      onDone();
    } catch (err) {
      setError(errorMessage(err));
    }
  }
  const needsBasis = level !== "unverified";
  return (
    <EntryCard entry={entry}>
      <div className="flex flex-wrap items-center gap-2">
        <Select aria-label="Verification level" className="w-auto" value={level} onChange={(e) => setLevel(e.target.value as LearnVerification)}>
          {(["unverified", "reviewed", "verified"] as const).map((v) => (
            <option key={v} value={v}>{LEARN_VERIFICATION_LABEL[v]}</option>
          ))}
        </Select>
        {needsBasis ? <Input aria-label="Verification basis" className="w-72" placeholder="Basis (datasheet, standard, test…)" value={basis} onChange={(e) => setBasis(e.target.value)} /> : null}
        <Input aria-label="Reviewer note" className="w-72" placeholder="Note to the contributor (optional)" value={note} onChange={(e) => setNote(e.target.value)} />
      </div>
      {error ? <p role="alert" className="text-xs text-danger">{error}</p> : null}
      <div className="flex gap-1.5 pt-1">
        <Button size="sm" disabled={needsBasis && !basis.trim()} onClick={() => void decide("approve")}>Approve</Button>
        <Button size="sm" variant="ghost" onClick={() => void decide("reject")}>Reject</Button>
      </div>
    </EntryCard>
  );
}

function Review() {
  const client = useApi();
  const queue = useAsync((s) => client.learn.reviewQueue({ limit: 50 }, s), [client]);
  return (
    <Panel>
      {queue.error ? <Failed what="the review queue" error={queue.error} onRetry={queue.reload} /> : !queue.data ? <Loading /> : queue.data.items.length === 0 ? (
        <EmptyState title="Nothing to review" description="Contributions appear here once their authors submit them. You can't review your own." />
      ) : (
        <ul className="divide-y divide-border">
          {queue.data.items.map((e) => (
            <ReviewItem key={e.id} entry={e} onDone={queue.reload} />
          ))}
        </ul>
      )}
    </Panel>
  );
}

// ------------------------------------------------------------------------------ insights

function Rows({ rows, label }: { rows: ({ key: string } & EvaluationTally)[]; label: string }) {
  if (!rows.length) return <p className="px-4 py-3 text-xs text-muted">No data yet.</p>;
  return (
    <Table>
      <THead>
        <TR>
          <TH>{label}</TH>
          <TH>Recommendations</TH>
          <TH>Accepted</TH>
          <TH>Rejected</TH>
          <TH>Helpful</TH>
          <TH>Findings resolved later</TH>
        </TR>
      </THead>
      <TBody>
        {rows.map((r) => (
          <TR key={r.key}>
            <TD>{r.key}</TD>
            <TD className="tabular-nums">{r.recommendations}</TD>
            <TD className="tabular-nums">{pct(r.acceptance_rate)}</TD>
            <TD className="tabular-nums">{pct(r.rejection_rate)}</TD>
            <TD className="tabular-nums">{pct(r.helpful_rate)}</TD>
            <TD className="tabular-nums">{r.evidence_resolved} of {r.evidence_resolved + r.evidence_persisting}</TD>
          </TR>
        ))}
      </TBody>
    </Table>
  );
}

function EvaluationView({ data }: { data: Evaluation }) {
  const s = data.summary;
  return (
    <div className="space-y-4">
      <div className="grid grid-cols-2 gap-2 md:grid-cols-4">
        {[
          ["Recommendations", String(s.recommendations)],
          ["Accepted of decided", pct(s.acceptance_rate)],
          ["Helpful of rated", pct(s.helpful_rate)],
          ["AI answers discarded as ungrounded", pct(data.grounding.rejection_rate)],
        ].map(([k, v]) => (
          <Panel key={k} className="p-3">
            <p className="text-xs text-muted">{k}</p>
            <p className="text-lg font-medium tabular-nums">{v}</p>
          </Panel>
        ))}
      </div>
      <Panel>
        <h3 className="px-4 pt-3 text-sm font-medium">By category</h3>
        <Rows label="Category" rows={data.by_category.map((r) => ({ ...r, key: r.category }))} />
      </Panel>
      <Panel>
        <h3 className="px-4 pt-3 text-sm font-medium">By engine and model version</h3>
        <Rows label="Model · prompt · engine" rows={data.by_version.map((r) => ({ ...r, key: `${r.model} · ${r.prompt_version} · ${r.engine_version ?? "n/a"}` }))} />
      </Panel>
      <Panel>
        <h3 className="px-4 pt-3 text-sm font-medium">By board size</h3>
        <Rows label="Board" rows={data.by_board_bucket.map((r) => ({ ...r, key: r.bucket }))} />
      </Panel>
      <Panel className="space-y-2 p-4">
        <h3 className="text-sm font-medium">What VIA cannot measure</h3>
        <ul className="space-y-1 text-xs text-muted">
          {data.not_measurable.map((n) => (
            <li key={n.metric}><span className="text-foreground">Not measurable: {n.metric}.</span> {n.reason}</li>
          ))}
          {data.notes.map((n) => <li key={n}>{n}</li>)}
          {data.capped ? <li>Only the most recent recommendations were counted.</li> : null}
        </ul>
      </Panel>
    </div>
  );
}

function Insights({ reviewer }: { reviewer: boolean }) {
  const client = useApi();
  const [scope, setScope] = useState<"mine" | "global">("mine");
  const result = useAsync((s) => (scope === "global" ? client.learn.globalEvaluation(s) : client.learn.evaluation(undefined, s)), [client, scope]);
  return (
    <>
      <div className="mb-3 flex items-center gap-2">
        <p className="text-xs text-muted">
          {scope === "global" ? "Counts and rates across all projects. No project or contributor detail." : "Your projects only."}
        </p>
        {reviewer ? (
          <Select aria-label="Scope" className="w-auto" value={scope} onChange={(e) => setScope(e.target.value as "mine" | "global")}>
            <option value="mine">My projects</option>
            <option value="global">All projects (reviewer)</option>
          </Select>
        ) : null}
      </div>
      {result.error ? <Failed what="insights" error={result.error} onRetry={result.reload} /> : !result.data ? <Loading /> : result.data.summary.recommendations === 0 ? (
        <>
          <EmptyState title="No recommendations to evaluate yet" description="Run an AI design review and give feedback on its recommendations." />
          <div className="mt-4"><EvaluationView data={result.data} /></div>
        </>
      ) : <EvaluationView data={result.data} />}
    </>
  );
}

// ------------------------------------------------------------------------------ feedback history

function FeedbackHistory() {
  const client = useApi();
  const result = useAsync((s) => client.learn.feedbackHistory({ mine: true, limit: 100 }, s), [client]);
  return (
    <Panel>
      {result.error ? <Failed what="feedback" error={result.error} onRetry={result.reload} /> : !result.data ? <Loading /> : result.data.items.length === 0 ? (
        <EmptyState title="No feedback yet" description="Feedback you give on AI recommendations appears here." />
      ) : (
        <ul className="divide-y divide-border">
          {result.data.items.map((f) => (
            <li key={f.id} className="space-y-0.5 px-4 py-2 text-sm">
              <div className="flex flex-wrap items-center gap-1.5">
                <Badge>{FEEDBACK_LABEL[f.feedback_type]}</Badge>
                <Badge>{f.category}</Badge>
                <span className="text-xs text-muted">{formatDateTime(f.created_at)}</span>
              </div>
              {f.explanation ? <p>{f.explanation}</p> : null}
              <p className="text-xs text-muted">{f.model} · prompt {f.prompt_version}{f.engine_version ? ` · engine ${f.engine_version}` : ""}</p>
            </li>
          ))}
        </ul>
      )}
    </Panel>
  );
}

// ------------------------------------------------------------------------------ page

export function LearnBrowser() {
  const { me } = useSession();
  const reviewer = Boolean(me?.user.learn_reviewer);
  const views = VIEWS.filter((v) => v !== "review" || reviewer);
  const { params, update } = useUrlParams();
  const view = pick(params.get("view"), views, "library");
  return (
    <>
      <PageHeader title="VIA Learn" description="Knowledge contributed by people, reviewed before use. Your projects stay private, and nothing is shared unless you choose to." />
      <nav aria-label="VIA Learn views" className="mb-4 flex flex-wrap gap-1 border-b border-border">
        {views.map((v) => (
          <button
            key={v}
            type="button"
            aria-current={view === v ? "page" : undefined}
            onClick={() => (view === v ? null : update({ view: v === "library" ? null : v, q: null, category: null, verification: null }))}
            className={cn("-mb-px border-b-2 px-3 py-2 text-[13px] transition-colors duration-100", view === v ? "border-accent font-medium text-foreground" : "border-transparent text-muted hover:text-foreground")}
          >
            {VIEW_LABEL[v]}
          </button>
        ))}
      </nav>
      {view === "library" ? <Library /> : view === "contributions" ? <Contributions /> : view === "review" ? <Review /> : view === "insights" ? <Insights reviewer={reviewer} /> : <FeedbackHistory />}
    </>
  );
}
