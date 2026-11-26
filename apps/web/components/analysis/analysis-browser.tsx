"use client";

import type { FindingListItem, RunListItem, Severity } from "@via/types";
import { Badge, Button, cn, EmptyState, ErrorState, Input, Mono, Panel, Select, Skeleton, StatusDot, type StatusTone } from "@via/ui";
import { ChevronLeft, ChevronRight, ScanSearch, Search, SearchX } from "lucide-react";
import Link from "next/link";
import { type ReactNode, useEffect, useState } from "react";

import { useApi } from "@/components/api-context";
import { PageHeader } from "@/components/app-shell";
import { errorMessage } from "@/lib/errors";
import { SEVERITIES, severityTone, SOURCE_LABEL, VERIFICATION_LABEL } from "@/lib/findings";
import { formatDateTime, relativeTime } from "@/lib/format";
import { useAsync } from "@/lib/use-async";
import { pick, useUrlParams } from "@/lib/use-url-params";

const PAGE_SIZE = 25;
const VIEWS = ["findings", "runs"] as const;
const FINDING_STATUSES = ["open", "reviewed", "dismissed", "all"] as const;
const RUN_STATUSES = ["all", "succeeded", "failed", "running", "queued"] as const;
const ACTIVE_RUN = new Set(["queued", "running"]);

function findingHref(f: FindingListItem) {
  return `/projects/${f.project.id}/designs/${f.design.id}?tab=analysis&revision=${f.revision_id}&finding=${f.id}`;
}

function Pager({ page, total, shown, onPage }: { page: number; total: number; shown: number; onPage: (p: number) => void }) {
  return (
    <>
      <span className="tabular-nums">
        {page * PAGE_SIZE + 1}–{page * PAGE_SIZE + shown} of {total}
      </span>
      <div className="flex gap-1">
        <Button size="sm" variant="ghost" disabled={page === 0} onClick={() => onPage(page - 1)} aria-label="Previous page">
          <ChevronLeft />
        </Button>
        <Button size="sm" variant="ghost" disabled={(page + 1) * PAGE_SIZE >= total} onClick={() => onPage(page + 1)} aria-label="Next page">
          <ChevronRight />
        </Button>
      </div>
    </>
  );
}

function ProjectFilter({ value, archived, onChange }: { value: string; archived: boolean; onChange: (v: string) => void }) {
  const client = useApi();
  const projects = useAsync((s) => client.projects.list({ status: archived ? "all" : "active", sort: "name", limit: 100 }, s), [client, archived]);
  return (
    <Select aria-label="Project" className="w-auto max-w-56" value={value} onChange={(e) => onChange(e.target.value)}>
      <option value="">All projects</option>
      {(projects.data?.items ?? []).map((p) => (
        <option key={p.id} value={p.id}>
          {p.name}
          {p.archived_at ? " (archived)" : ""}
        </option>
      ))}
    </Select>
  );
}

function ArchivedToggle({ checked, onChange }: { checked: boolean; onChange: (v: boolean) => void }) {
  return (
    <label className="flex h-8 items-center gap-1.5 text-xs text-muted">
      <input type="checkbox" checked={checked} onChange={(e) => onChange(e.target.checked)} className="size-3.5 accent-accent" />
      Include archived
    </label>
  );
}

function Loading() {
  return (
    <div className="space-y-2 p-4">
      {Array.from({ length: 6 }, (_, i) => (
        <Skeleton key={i} className="h-8 w-full" />
      ))}
    </div>
  );
}

function Failed({ what, error, onRetry }: { what: string; error: unknown; onRetry: () => void }) {
  return (
    <ErrorState
      className="m-4"
      title={`Couldn't load ${what}`}
      description={errorMessage(error)}
      action={
        <Button size="sm" onClick={onRetry}>
          Retry
        </Button>
      }
    />
  );
}

// ----------------------------------------------------------------------------- findings

function FindingsView() {
  const client = useApi();
  const { params, update, page } = useUrlParams();
  const severity = pick<Severity | "">(params.get("severity"), ["", ...SEVERITIES], "");
  const status = pick(params.get("status"), FINDING_STATUSES, "open");
  const projectId = params.get("project") ?? "";
  const archived = params.get("archived") === "1";
  const q = params.get("q") ?? "";
  const [search, setSearch] = useState(q);
  useEffect(() => {
    if (search === q) return;
    const id = window.setTimeout(() => update({ q: search.trim() || null }), 250);
    return () => window.clearTimeout(id);
  }, [search, q, update]);

  const result = useAsync(
    (s) =>
      client.analysis.browseFindings(
        {
          severity: severity || undefined, status, q: q || undefined, project_id: projectId || undefined, include_archived: archived,
          limit: PAGE_SIZE, offset: page * PAGE_SIZE,
        },
        s,
      ),
    [client, severity, status, q, projectId, archived, page],
  );
  const data = result.data;

  return (
    <>
      <div role="group" aria-label="Filter by severity" className="mb-3 grid grid-cols-3 overflow-hidden rounded-lg border border-border bg-surface sm:grid-cols-5">
        {SEVERITIES.map((s, i) => {
          const active = severity === s;
          return (
            <button
              key={s}
              type="button"
              aria-pressed={active}
              onClick={() => update({ severity: active ? null : s })}
              className={cn(
                "flex flex-col items-start gap-0.5 border-border px-4 py-2.5 text-left transition-colors duration-100 hover:bg-surface-hover",
                i > 0 && "border-l",
                i === 3 && "max-sm:border-l-0 max-sm:border-t",
                i === 4 && "max-sm:border-t",
                active && "bg-accent-soft hover:bg-accent-soft",
              )}
            >
              <span className="flex items-center gap-1.5 text-xs capitalize text-muted">
                <Badge tone={severityTone(s)} className="px-1">
                  {s}
                </Badge>
              </span>
              <span className="font-mono text-lg font-medium leading-7 tabular-nums text-foreground">
                {data ? (data.by_severity[s] ?? 0) : <Skeleton className="my-1 h-5 w-8" />}
              </span>
            </button>
          );
        })}
      </div>

      <div className="mb-3 flex flex-wrap items-center gap-2">
        <div className="relative min-w-56 flex-1">
          <Search className="pointer-events-none absolute top-1/2 left-2.5 size-3.5 -translate-y-1/2 text-subtle" aria-hidden="true" />
          <Input type="search" aria-label="Search findings" placeholder="Title or rule, or an exact reference or net (R12, +3V3)" className="pl-8" maxLength={100} value={search} onChange={(e) => setSearch(e.target.value)} />
        </div>
        <Select aria-label="Review status" className="w-auto" value={status} onChange={(e) => update({ status: e.target.value === "open" ? null : e.target.value })}>
          <option value="open">Open</option>
          <option value="reviewed">Reviewed</option>
          <option value="dismissed">Dismissed</option>
          <option value="all">Any status</option>
        </Select>
        <ProjectFilter value={projectId} archived={archived} onChange={(v) => update({ project: v || null })} />
        <ArchivedToggle checked={archived} onChange={(v) => update({ archived: v ? "1" : null, project: null })} />
      </div>

      <Panel
        aria-busy={result.loading}
        title="Findings"
        meta={data ? `latest analysis of ${data.designs_analysed} ${data.designs_analysed === 1 ? "design" : "designs"}` : undefined}
        footer={data && data.total > 0 ? <Pager page={page} total={data.total} shown={data.items.length} onPage={(p) => update({ page: p ? String(p) : null })} /> : undefined}
      >
        {result.error ? (
          <Failed what="findings" error={result.error} onRetry={result.reload} />
        ) : !data ? (
          <Loading />
        ) : data.items.length === 0 ? (
          data.designs_analysed === 0 ? (
            <EmptyState icon={<ScanSearch />} title="No analyses yet" description="Open a design and run an analysis from its Analysis tab. Its findings will appear here." />
          ) : (
            <EmptyState icon={<SearchX />} title={status === "open" && !q && !severity ? "No open findings" : "No matching findings"} description={status === "open" && !q && !severity ? "Every finding in the latest analyses has been reviewed or dismissed." : "Try a different search or filter."} />
          )
        ) : (
          <ul className={cn("divide-y divide-border", result.loading && "opacity-60")} aria-label="Findings">
            {data.items.map((f) => (
              <li key={f.id}>
                <Link href={findingHref(f)} className="flex gap-3 px-4 py-2.5 hover:bg-surface-hover">
                  <Badge tone={severityTone(f.severity)} className="mt-0.5 h-5 w-16 shrink-0 self-start justify-center capitalize">
                    {f.severity}
                  </Badge>
                  <div className="min-w-0 flex-1">
                    <p className="truncate text-[13px] font-medium text-foreground">{f.title}</p>
                    <p className="flex min-w-0 flex-wrap items-center gap-x-2 gap-y-0.5 text-xs text-subtle">
                      <Mono className="text-muted">{f.rule}</Mono>
                      <span>{SOURCE_LABEL[f.source]}</span>
                      <span>{VERIFICATION_LABEL[f.verification]}</span>
                      {f.components.length ? <Mono>{f.components.slice(0, 4).join(", ")}{f.components.length > 4 ? "…" : ""}</Mono> : null}
                      {f.nets.length ? <Mono>{f.nets.slice(0, 2).join(", ")}{f.nets.length > 2 ? "…" : ""}</Mono> : null}
                      {f.status !== "open" ? <Badge>{f.status}</Badge> : null}
                    </p>
                  </div>
                  <div className="hidden w-48 shrink-0 text-right sm:block">
                    <p className="truncate text-[13px] text-foreground">{f.design.name}</p>
                    <p className="truncate text-xs text-subtle">
                      {f.project.name} · <Mono>r{f.revision_number}</Mono>
                    </p>
                  </div>
                </Link>
              </li>
            ))}
          </ul>
        )}
      </Panel>
    </>
  );
}

// --------------------------------------------------------------------------------- runs

const RUN_TONE: Record<RunListItem["status"], StatusTone> = { succeeded: "ok", failed: "error", running: "accent", queued: "accent" };
const RUN_LABEL: Record<RunListItem["status"], string> = { succeeded: "Succeeded", failed: "Failed", running: "Running", queued: "Queued" };

function SeverityCounts({ run }: { run: RunListItem }): ReactNode {
  if (run.status === "failed") return <span className="text-xs text-danger">{run.error_code ?? "Failed"}</span>;
  if (run.finding_count === null) return <span className="text-xs text-subtle">–</span>;
  return (
    <span className="flex flex-wrap items-center gap-1">
      <Mono className="mr-1">{run.finding_count}</Mono>
      {SEVERITIES.map((s) =>
        run.by_severity[s] ? (
          <Badge key={s} tone={severityTone(s)}>
            {run.by_severity[s]} {s}
          </Badge>
        ) : null,
      )}
    </span>
  );
}

function RunsView() {
  const client = useApi();
  const { params, update, page } = useUrlParams();
  const status = pick(params.get("status"), RUN_STATUSES, "all");
  const projectId = params.get("project") ?? "";
  const archived = params.get("archived") === "1";
  const result = useAsync(
    (s) =>
      client.analysis.browseRuns(
        { status: status === "all" ? undefined : status, project_id: projectId || undefined, include_archived: archived, limit: PAGE_SIZE, offset: page * PAGE_SIZE },
        s,
      ),
    [client, status, projectId, archived, page],
  );
  const data = result.data;
  const active = data?.items.some((r) => ACTIVE_RUN.has(r.status)) ?? false;
  const { reload } = result;
  useEffect(() => {
    if (!active) return;
    const id = window.setTimeout(reload, 3000);
    return () => window.clearTimeout(id);
  }, [active, data, reload]);

  return (
    <>
      <div className="mb-3 flex flex-wrap items-center gap-2">
        <Select aria-label="Run status" className="w-auto" value={status} onChange={(e) => update({ status: e.target.value === "all" ? null : e.target.value })}>
          <option value="all">Any status</option>
          <option value="succeeded">Succeeded</option>
          <option value="failed">Failed</option>
          <option value="running">Running</option>
          <option value="queued">Queued</option>
        </Select>
        <ProjectFilter value={projectId} archived={archived} onChange={(v) => update({ project: v || null })} />
        <ArchivedToggle checked={archived} onChange={(v) => update({ archived: v ? "1" : null, project: null })} />
      </div>
      <Panel
        aria-busy={result.loading}
        title="Analysis runs"
        meta={data ? `${data.total} total` : undefined}
        footer={data && data.total > 0 ? <Pager page={page} total={data.total} shown={data.items.length} onPage={(p) => update({ page: p ? String(p) : null })} /> : undefined}
      >
        {result.error ? (
          <Failed what="analysis runs" error={result.error} onRetry={result.reload} />
        ) : !data ? (
          <Loading />
        ) : data.items.length === 0 ? (
          <EmptyState icon={<ScanSearch />} title={status === "all" && !projectId ? "No analyses yet" : "No matching runs"} description={status === "all" && !projectId ? "Open a design and run an analysis from its Analysis tab." : "Try a different filter."} />
        ) : (
          <ul className={cn("divide-y divide-border", result.loading && "opacity-60")} aria-label="Analysis runs">
            {data.items.map((r) => (
              <li key={r.id} className="grid grid-cols-[minmax(0,1fr)_auto] items-center gap-x-4 gap-y-1 px-4 py-2.5 md:grid-cols-[112px_minmax(0,1fr)_minmax(0,1.2fr)_140px]">
                <span className="inline-flex items-center gap-1.5 text-xs text-muted">
                  <StatusDot tone={RUN_TONE[r.status]} />
                  {RUN_LABEL[r.status]}
                </span>
                <span className="order-first min-w-0 md:order-none">
                  <Link href={`/projects/${r.project.id}/designs/${r.design.id}?tab=analysis&revision=${r.revision_id}`} className="block truncate text-[13px] font-medium text-foreground hover:underline">
                    {r.design.name} <Mono className="text-subtle">r{r.revision_number}</Mono>
                  </Link>
                  <span className="block truncate text-xs text-subtle">
                    {r.project.name}
                    {r.project_archived ? " (archived)" : ""}
                  </span>
                </span>
                <span className="col-span-2 md:col-span-1">
                  <SeverityCounts run={r} />
                </span>
                <span className="col-span-2 text-xs text-subtle md:col-span-1 md:text-right" title={formatDateTime(r.finished_at ?? r.created_at)}>
                  {r.triggered_by ? `${r.triggered_by.display_name} · ` : ""}
                  <time dateTime={r.finished_at ?? r.created_at}>{relativeTime(r.finished_at ?? r.created_at)}</time>
                </span>
              </li>
            ))}
          </ul>
        )}
      </Panel>
    </>
  );
}

// --------------------------------------------------------------------------------- page

export function AnalysisBrowser() {
  const { params, update } = useUrlParams();
  const view = pick(params.get("view"), VIEWS, "findings");
  return (
    <>
      <PageHeader title="Analysis" description="Findings from the latest analysis of each design, and every analysis run, across your projects." />
      <nav aria-label="Analysis views" className="mb-4 flex gap-1 border-b border-border">
        {VIEWS.map((v) => (
          <button
            key={v}
            type="button"
            aria-current={view === v ? "page" : undefined}
            onClick={() => (view === v ? null : update({ view: v === "findings" ? null : v, status: null, severity: null, q: null }))}
            className={cn(
              "-mb-px border-b-2 px-3 py-2 text-[13px] capitalize transition-colors duration-100",
              view === v ? "border-accent font-medium text-foreground" : "border-transparent text-muted hover:text-foreground",
            )}
          >
            {v}
          </button>
        ))}
      </nav>
      {view === "findings" ? <FindingsView key="findings" /> : <RunsView key="runs" />}
    </>
  );
}
