"use client";

import type { DesignListItem, DesignSort, DesignStatusFilter, RevisionBrief } from "@via/types";
import { Badge, Button, cn, EmptyState, ErrorState, Input, Mono, Panel, Select, Skeleton, StatusDot, type StatusTone } from "@via/ui";
import { ChevronLeft, ChevronRight, CircuitBoard, Search, SearchX } from "lucide-react";
import Link from "next/link";
import { usePathname, useRouter, useSearchParams } from "next/navigation";
import { useEffect, useState } from "react";

import { useApi } from "@/components/api-context";
import { PageHeader } from "@/components/app-shell";
import { UploadShortcut } from "@/components/designs/upload-shortcut";
import { errorMessage } from "@/lib/errors";
import { formatDateTime, relativeTime } from "@/lib/format";
import { useAsync } from "@/lib/use-async";

const PAGE_SIZE = 25;
const STATUSES: { value: DesignStatusFilter; label: string }[] = [
  { value: "all", label: "All" },
  { value: "ready", label: "Imported" },
  { value: "processing", label: "Importing" },
  { value: "failed", label: "Failed" },
];
const SORTS: { value: DesignSort; label: string }[] = [
  { value: "updated", label: "Last updated" },
  { value: "created", label: "Newest" },
  { value: "name", label: "Name" },
];

function pick<T extends string>(value: string | null, allowed: readonly T[], fallback: T): T {
  return allowed.includes(value as T) ? (value as T) : fallback;
}

const UPLOAD: Record<RevisionBrief["status"], { label: string; tone: StatusTone }> = {
  pending: { label: "Queued", tone: "accent" },
  processing: { label: "Importing", tone: "accent" },
  ready: { label: "Imported", tone: "ok" },
  failed: { label: "Import failed", tone: "error" },
};

function designHref(d: DesignListItem, tab?: string) {
  return `/projects/${d.project.id}/designs/${d.id}${tab ? `?tab=${tab}` : ""}`;
}

/** Most recent upload. If it failed or is still importing, say which revision is being shown instead. */
function UploadCell({ d }: { d: DesignListItem }) {
  const latest = d.latest_revision;
  if (!latest) return <span className="text-xs text-subtle">No uploads</span>;
  const s = UPLOAD[latest.status];
  const showing = d.current_revision && d.current_revision.id !== latest.id ? d.current_revision.revision_number : null;
  return (
    <span className="inline-flex flex-wrap items-center gap-x-1.5 text-xs text-muted" title={formatDateTime(latest.created_at)}>
      <StatusDot tone={s.tone} />
      <span className="whitespace-nowrap">{s.label}</span>
      <Mono className="text-subtle">r{latest.revision_number}</Mono>
      {showing !== null ? <span className="whitespace-nowrap text-subtle">(showing r{showing})</span> : null}
    </span>
  );
}

function AnalysisCell({ d }: { d: DesignListItem }) {
  const a = d.latest_analysis;
  if (!a) return <span className="text-xs text-subtle">Not analysed</span>;
  const tone: StatusTone = a.status === "succeeded" ? (a.finding_count ? "warning" : "ok") : a.status === "failed" ? "error" : "accent";
  const label =
    a.status === "succeeded" ? (
      <>
        <Mono>{a.finding_count ?? 0}</Mono> {a.finding_count === 1 ? "finding" : "findings"}
      </>
    ) : a.status === "failed" ? (
      "Failed"
    ) : a.status === "queued" ? (
      "Queued"
    ) : (
      "Running"
    );
  return (
    <Link href={designHref(d, "analysis")} title={`Revision ${a.revision_number}: ${formatDateTime(a.at)}`} className="inline-flex items-center gap-1.5 whitespace-nowrap text-xs text-muted hover:text-foreground">
      <StatusDot tone={tone} />
      <span>{label}</span>
      <Mono className="text-subtle">r{a.revision_number}</Mono>
    </Link>
  );
}

function count(rev: RevisionBrief | null, key: "component_count" | "net_count" | "copper_layer_count") {
  const v = rev?.object_counts[key];
  return typeof v === "number" ? <Mono>{v}</Mono> : <span className="text-subtle">–</span>;
}

export function DesignsBrowser() {
  const client = useApi();
  const router = useRouter();
  const pathname = usePathname();
  const params = useSearchParams();
  const status = pick(params.get("status"), STATUSES.map((s) => s.value), "all");
  const sort = pick(params.get("sort"), SORTS.map((s) => s.value), "updated");
  const projectId = params.get("project") ?? "";
  const archived = params.get("archived") === "1";
  const q = params.get("q") ?? "";
  const page = Math.max(0, Number.parseInt(params.get("page") ?? "0", 10) || 0);
  const [search, setSearch] = useState(q);

  function update(changes: Record<string, string | null>) {
    const next = new URLSearchParams(params.toString());
    for (const [k, v] of Object.entries(changes)) {
      if (v === null || v === "") next.delete(k);
      else next.set(k, v);
    }
    if (!("page" in changes)) next.delete("page");
    const s = next.toString();
    router.replace(s ? `${pathname}?${s}` : pathname, { scroll: false });
  }

  useEffect(() => {
    if (search === q) return;
    const id = window.setTimeout(() => update({ q: search.trim() || null }), 250);
    return () => window.clearTimeout(id);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [search]);

  const projects = useAsync((s) => client.projects.list({ status: archived ? "all" : "active", sort: "name", limit: 100 }, s), [client, archived]);
  const result = useAsync(
    (signal) =>
      client.designs.browse(
        { q: q || undefined, status, sort, project_id: projectId || undefined, include_archived: archived, limit: PAGE_SIZE, offset: page * PAGE_SIZE },
        signal,
      ),
    [client, q, status, sort, projectId, archived, page],
  );
  const data = result.data;
  // Keep importing rows current: refresh while any upload on this page is queued or importing.
  const importing = data?.items.some((d) => d.latest_revision && ["pending", "processing"].includes(d.latest_revision.status)) ?? false;
  const { reload } = result;
  useEffect(() => {
    if (!importing) return;
    const id = window.setTimeout(reload, 3000);
    return () => window.clearTimeout(id);
  }, [importing, data, reload]);
  const filtered = Boolean(q) || status !== "all" || Boolean(projectId);

  return (
    <>
      <PageHeader title="Designs" description="PCB designs across every project you can access." actions={<UploadShortcut />} />

      <div className="mb-3 flex flex-wrap items-center gap-2">
        <div className="relative min-w-56 flex-1">
          <Search className="pointer-events-none absolute top-1/2 left-2.5 size-3.5 -translate-y-1/2 text-subtle" aria-hidden="true" />
          <Input
            type="search"
            aria-label="Search designs"
            placeholder="Search design or project name"
            className="pl-8"
            maxLength={100}
            value={search}
            onChange={(e) => setSearch(e.target.value)}
          />
        </div>
        <div role="group" aria-label="Upload status" className="flex h-8 items-center rounded-md border border-border-strong bg-surface p-0.5">
          {STATUSES.map((s) => (
            <button
              key={s.value}
              type="button"
              aria-pressed={status === s.value}
              onClick={() => update({ status: s.value === "all" ? null : s.value })}
              className={cn(
                "h-full rounded-sm px-2.5 text-xs transition-colors duration-100",
                status === s.value ? "bg-accent-soft font-medium text-foreground" : "text-muted hover:text-foreground",
              )}
            >
              {s.label}
            </button>
          ))}
        </div>
        <Select aria-label="Project" className="w-auto max-w-56" value={projectId} onChange={(e) => update({ project: e.target.value || null })}>
          <option value="">All projects</option>
          {(projects.data?.items ?? []).map((p) => (
            <option key={p.id} value={p.id}>
              {p.name}
              {p.archived_at ? " (archived)" : ""}
            </option>
          ))}
        </Select>
        <Select aria-label="Sort by" className="w-auto" value={sort} onChange={(e) => update({ sort: e.target.value === "updated" ? null : e.target.value })}>
          {SORTS.map((s) => (
            <option key={s.value} value={s.value}>
              {s.label}
            </option>
          ))}
        </Select>
        <label className="flex h-8 items-center gap-1.5 text-xs text-muted">
          <input type="checkbox" checked={archived} onChange={(e) => update({ archived: e.target.checked ? "1" : null, project: null })} className="size-3.5 accent-accent" />
          Include archived
        </label>
      </div>

      {result.error ? (
        <ErrorState
          title="Couldn't load designs"
          description={errorMessage(result.error)}
          action={
            <Button size="sm" onClick={result.reload}>
              Retry
            </Button>
          }
        />
      ) : (
        <Panel
          aria-busy={result.loading}
          footer={
            data && data.total > 0 ? (
              <>
                <span className="tabular-nums">
                  {page * PAGE_SIZE + 1}–{page * PAGE_SIZE + data.items.length} of {data.total}
                </span>
                <div className="flex gap-1">
                  <Button size="sm" variant="ghost" disabled={page === 0} onClick={() => update({ page: page - 1 ? String(page - 1) : null })} aria-label="Previous page">
                    <ChevronLeft />
                  </Button>
                  <Button size="sm" variant="ghost" disabled={(page + 1) * PAGE_SIZE >= data.total} onClick={() => update({ page: String(page + 1) })} aria-label="Next page">
                    <ChevronRight />
                  </Button>
                </div>
              </>
            ) : undefined
          }
        >
          {!data ? (
            <div className="space-y-2 p-4">
              {Array.from({ length: 6 }, (_, i) => (
                <Skeleton key={i} className="h-8 w-full" />
              ))}
            </div>
          ) : data.items.length === 0 ? (
            filtered ? (
              <EmptyState icon={<SearchX />} title="No matching designs" description="Try a different search or filter." />
            ) : (
              <EmptyState
                icon={<CircuitBoard />}
                title="No designs yet"
                description="Upload a KiCad board (.kicad_pcb or a zipped project) into a project to see it here."
                action={<UploadShortcut />}
              />
            )
          ) : (
            <>
              <table className={cn("hidden w-full table-fixed text-[13px] md:table", result.loading && "opacity-60")}>
                <caption className="sr-only">Designs</caption>
                <colgroup>
                  <col />
                  <col className="w-[168px]" />
                  <col className="hidden w-[92px] lg:table-column" />
                  <col className="hidden w-[64px] lg:table-column" />
                  <col className="hidden w-[72px] lg:table-column" />
                  <col className="w-[148px]" />
                  <col className="w-[96px]" />
                </colgroup>
                <thead className="border-b border-border bg-surface-sunken text-left text-xs text-muted">
                  <tr>
                    <th scope="col" className="h-8 pl-4 pr-3 font-medium">Design</th>
                    <th scope="col" className="h-8 px-3 font-medium">Last upload</th>
                    <th scope="col" className="hidden h-8 px-3 text-right font-medium lg:table-cell">Components</th>
                    <th scope="col" className="hidden h-8 px-3 text-right font-medium lg:table-cell">Nets</th>
                    <th scope="col" className="hidden h-8 px-3 text-right font-medium lg:table-cell" title="Copper layers">Layers</th>
                    <th scope="col" className="h-8 px-3 font-medium">Last analysis</th>
                    <th scope="col" className="h-8 pl-3 pr-4 text-right font-medium">Updated</th>
                  </tr>
                </thead>
                <tbody>
                  {data.items.map((d) => (
                    <tr key={d.id} className="border-b border-border last:border-0 hover:bg-surface-hover">
                      <td className="py-1.5 pl-4 pr-3">
                        <Link href={designHref(d)} className="block truncate font-medium text-foreground hover:underline">
                          {d.name}
                        </Link>
                        <span className="flex min-w-0 items-center gap-1.5 text-xs text-subtle">
                          <Link href={`/projects/${d.project.id}`} className="truncate hover:text-foreground hover:underline">
                            {d.project.name}
                          </Link>
                          {d.project_archived ? <Badge>Archived</Badge> : null}
                          <span aria-hidden="true">·</span>
                          <span className="shrink-0">
                            <Mono>{d.revision_count}</Mono> {d.revision_count === 1 ? "revision" : "revisions"}
                          </span>
                        </span>
                      </td>
                      <td className="px-3">
                        <UploadCell d={d} />
                      </td>
                      <td className="hidden px-3 text-right lg:table-cell">{count(d.current_revision, "component_count")}</td>
                      <td className="hidden px-3 text-right lg:table-cell">{count(d.current_revision, "net_count")}</td>
                      <td className="hidden px-3 text-right lg:table-cell">{count(d.current_revision, "copper_layer_count")}</td>
                      <td className="px-3">
                        <AnalysisCell d={d} />
                      </td>
                      <td className="whitespace-nowrap pl-3 pr-4 text-right text-xs text-subtle tabular-nums">
                        <time dateTime={d.updated_at} title={formatDateTime(d.updated_at)}>
                          {relativeTime(d.updated_at)}
                        </time>
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
              <ul className="divide-y divide-border md:hidden" aria-label="Designs">
                {data.items.map((d) => (
                  <li key={d.id} className="px-4 py-2.5">
                    <div className="flex items-baseline gap-2">
                      <Link href={designHref(d)} className="min-w-0 flex-1 truncate text-sm font-medium text-foreground hover:underline">
                        {d.name}
                      </Link>
                      <time dateTime={d.updated_at} className="shrink-0 text-xs text-subtle tabular-nums">
                        {relativeTime(d.updated_at)}
                      </time>
                    </div>
                    <p className="truncate text-xs text-subtle">{d.project.name}</p>
                    <div className="mt-1 flex flex-wrap items-center gap-x-3 gap-y-1">
                      <UploadCell d={d} />
                      <AnalysisCell d={d} />
                    </div>
                  </li>
                ))}
              </ul>
            </>
          )}
        </Panel>
      )}
    </>
  );
}
