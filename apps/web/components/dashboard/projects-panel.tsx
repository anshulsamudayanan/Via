"use client";

import type { ProjectSort } from "@via/types";
import { Button, cn, EmptyState, ErrorState, Mono, Panel, Skeleton } from "@via/ui";
import { ArrowDown, ArrowRight, ArrowUp, FolderKanban, Search } from "lucide-react";
import Link from "next/link";
import { useEffect, useState } from "react";

import { useApi } from "@/components/api-context";
import { RoleBadge } from "@/components/projects/badges";
import { errorMessage } from "@/lib/errors";
import { formatDateTime, relativeTime } from "@/lib/format";
import { useAsync } from "@/lib/use-async";

import { LastAnalysis, LastImport } from "./project-status";

const LIMIT = 8;
const SORT_LABEL: Record<ProjectSort, string> = { updated: "Last updated", created: "Newest", name: "Name" };

function useDebounced<T>(value: T, ms: number): T {
  const [v, setV] = useState(value);
  useEffect(() => {
    const t = setTimeout(() => setV(value), ms);
    return () => clearTimeout(t);
  }, [value, ms]);
  return v;
}

function SortHeader({ label, sort, current, onSort, className }: { label: string; sort: ProjectSort; current: ProjectSort; onSort: (s: ProjectSort) => void; className?: string }) {
  const active = current === sort;
  const Arrow = sort === "name" ? ArrowUp : ArrowDown;
  return (
    <th scope="col" aria-sort={active ? (sort === "name" ? "ascending" : "descending") : "none"} className={cn("h-8 px-3 font-medium", className)}>
      <button type="button" onClick={() => onSort(sort)} className={cn("inline-flex items-center gap-1 rounded-sm hover:text-foreground", active && "text-foreground")}>
        {label}
        {active ? <Arrow className="size-3" aria-hidden="true" /> : null}
      </button>
    </th>
  );
}

/** Recent active projects with their latest import and analysis; server-side search and sort. */
export function ProjectsPanel() {
  const client = useApi();
  const [query, setQuery] = useState("");
  const [sort, setSort] = useState<ProjectSort>("updated");
  const q = useDebounced(query.trim(), 250);
  const page = useAsync((s) => client.projects.list({ q: q || undefined, status: "active", sort, limit: LIMIT }, s), [client, q, sort]);
  const items = page.data?.items ?? [];

  return (
    <Panel
      title="Projects"
      meta={page.data ? `${page.data.total} active` : undefined}
      actions={
        <>
          <label className="relative hidden sm:block">
            <span className="sr-only">Filter projects</span>
            <Search className="pointer-events-none absolute left-2 top-1/2 size-3.5 -translate-y-1/2 text-subtle" aria-hidden="true" />
            <input
              type="search"
              value={query}
              onChange={(e) => setQuery(e.target.value)}
              placeholder="Filter projects"
              className="h-7 w-44 rounded-md border border-border bg-surface-sunken pl-7 pr-2 text-xs text-foreground outline-none placeholder:text-subtle focus:border-border-strong"
            />
          </label>
          <label className="flex items-center gap-1.5 text-xs text-subtle">
            <span className="sr-only sm:not-sr-only">Sort</span>
            <select
              value={sort}
              onChange={(e) => setSort(e.target.value as ProjectSort)}
              className="h-7 cursor-pointer rounded-md border border-border bg-surface-sunken px-1.5 text-xs text-foreground outline-none focus:border-border-strong"
            >
              {(Object.keys(SORT_LABEL) as ProjectSort[]).map((s) => (
                <option key={s} value={s}>
                  {SORT_LABEL[s]}
                </option>
              ))}
            </select>
          </label>
        </>
      }
      footer={
        page.data && page.data.total > 0 ? (
          <>
            <span className="tabular-nums">
              Showing {items.length} of {page.data.total}
            </span>
            <Link href="/projects" className="inline-flex items-center gap-1 text-muted hover:text-foreground">
              All projects <ArrowRight className="size-3" aria-hidden="true" />
            </Link>
          </>
        ) : undefined
      }
    >
      {/* Narrow screens: search lives in its own row. */}
      <div className="border-b border-border p-2 sm:hidden">
        <input
          type="search"
          aria-label="Filter projects"
          value={query}
          onChange={(e) => setQuery(e.target.value)}
          placeholder="Filter projects"
          className="h-8 w-full rounded-md border border-border bg-surface-sunken px-2 text-sm text-foreground outline-none placeholder:text-subtle focus:border-border-strong"
        />
      </div>
      {page.error ? (
        <ErrorState
          className="m-4"
          title="Couldn't load projects"
          description={errorMessage(page.error)}
          action={
            <Button size="sm" onClick={page.reload}>
              Retry
            </Button>
          }
        />
      ) : !page.data ? (
        <div className="space-y-2 p-4" aria-busy="true">
          {Array.from({ length: 4 }, (_, i) => (
            <Skeleton key={i} className="h-8 w-full" />
          ))}
        </div>
      ) : items.length === 0 ? (
        <EmptyState
          icon={<FolderKanban />}
          title={q ? `No active projects match “${q}”` : "No active projects"}
          description={q ? "Try another name, or search archived projects on the Projects page." : "Archived projects are listed on the Projects page."}
        />
      ) : (
        <>
          <table className={cn("hidden w-full table-fixed text-[13px] md:table", page.loading && "opacity-60")}>
            <colgroup>
              <col />
              <col className="w-[76px]" />
              <col className="w-[132px]" />
              <col className="w-[128px]" />
              <col className="hidden w-[88px] lg:table-column" />
              <col className="w-[96px]" />
            </colgroup>
            <thead className="border-b border-border bg-surface-sunken text-left text-xs text-muted">
              <tr>
                <SortHeader label="Project" sort="name" current={sort} onSort={setSort} className="pl-4" />
                <th scope="col" className="h-8 px-3 text-right font-medium">Designs</th>
                <th scope="col" className="h-8 px-3 font-medium">Last import</th>
                <th scope="col" className="h-8 px-3 font-medium">Last analysis</th>
                <th scope="col" className="hidden h-8 px-3 font-medium lg:table-cell">Role</th>
                <SortHeader label="Updated" sort="updated" current={sort} onSort={setSort} className="pr-4 text-right" />
              </tr>
            </thead>
            <tbody>
              {items.map((p) => (
                <tr key={p.id} className="border-b border-border last:border-0 hover:bg-surface-hover">
                  <td className="py-1.5 pl-4 pr-3">
                    <Link href={`/projects/${p.id}`} className="block truncate font-medium text-foreground hover:underline">
                      {p.name}
                    </Link>
                    <span className="block truncate text-xs text-subtle">{p.description || "No description"}</span>
                  </td>
                  <td className="px-3 text-right">
                    <Mono>{p.design_count}</Mono>
                  </td>
                  <td className="px-3">
                    <LastImport projectId={p.id} value={p.latest_import} />
                  </td>
                  <td className="px-3">
                    <LastAnalysis projectId={p.id} value={p.latest_analysis} />
                  </td>
                  <td className="hidden px-3 lg:table-cell">
                    <RoleBadge role={p.my_role} />
                  </td>
                  <td className="whitespace-nowrap pl-3 pr-4 text-right text-xs text-subtle tabular-nums">
                    <time dateTime={p.updated_at} title={formatDateTime(p.updated_at)}>
                      {relativeTime(p.updated_at)}
                    </time>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
          <ul className="divide-y divide-border md:hidden" aria-label="Projects">
            {items.map((p) => (
              <li key={p.id} className="px-4 py-2.5">
                <div className="flex items-baseline gap-2">
                  <Link href={`/projects/${p.id}`} className="min-w-0 flex-1 truncate text-sm font-medium text-foreground hover:underline">
                    {p.name}
                  </Link>
                  <time dateTime={p.updated_at} className="shrink-0 text-xs text-subtle tabular-nums">
                    {relativeTime(p.updated_at)}
                  </time>
                </div>
                <div className="mt-1 flex flex-wrap items-center gap-x-3 gap-y-1">
                  <span className="text-xs text-muted">
                    <Mono>{p.design_count}</Mono> {p.design_count === 1 ? "design" : "designs"}
                  </span>
                  <LastImport projectId={p.id} value={p.latest_import} />
                  <LastAnalysis projectId={p.id} value={p.latest_analysis} />
                </div>
              </li>
            ))}
          </ul>
        </>
      )}
    </Panel>
  );
}
