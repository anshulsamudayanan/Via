"use client";

import type { PartListItem, PartSort } from "@via/types";
import { Button, cn, EmptyState, ErrorState, Input, Mono, Panel, Select, Skeleton } from "@via/ui";
import { Boxes, ChevronLeft, ChevronRight, Search, SearchX } from "lucide-react";
import Link from "next/link";
import { useEffect, useState } from "react";

import { useApi } from "@/components/api-context";
import { PageHeader } from "@/components/app-shell";
import { errorMessage } from "@/lib/errors";
import { useAsync } from "@/lib/use-async";
import { pick, useUrlParams } from "@/lib/use-url-params";

const PAGE_SIZE = 50;
const SORTS: { value: PartSort; label: string }[] = [
  { value: "placements", label: "Most placed" },
  { value: "value", label: "Value" },
  { value: "footprint", label: "Footprint" },
];

/** KiCad footprints are "Library:Name"; show the name prominently and the library dimmed. */
function Footprint({ id }: { id: string }) {
  const at = id.indexOf(":");
  if (at < 0) return <Mono className="text-foreground">{id}</Mono>;
  return (
    <Mono className="block truncate" title={id}>
      <span className="text-subtle">{id.slice(0, at + 1)}</span>
      <span className="text-foreground">{id.slice(at + 1)}</span>
    </Mono>
  );
}

function designLink(part: PartListItem, d: PartListItem["designs"][number]) {
  const q = part.value ?? part.footprint;
  return `/projects/${d.project_id}/designs/${d.id}?tab=components&q=${encodeURIComponent(q)}`;
}

function Designs({ part }: { part: PartListItem }) {
  const extra = part.design_count - part.designs.length;
  return (
    <span className="flex min-w-0 flex-wrap gap-x-2 gap-y-0.5 text-xs">
      {part.designs.map((d) => (
        <Link key={d.id} href={designLink(part, d)} className="truncate text-muted hover:text-foreground hover:underline">
          {d.name}
        </Link>
      ))}
      {extra > 0 ? <span className="text-subtle">+{extra} more</span> : null}
    </span>
  );
}

export function PartsBrowser() {
  const client = useApi();
  const { params, update, page } = useUrlParams();
  const sort = pick(params.get("sort"), SORTS.map((s) => s.value), "placements");
  const projectId = params.get("project") ?? "";
  const archived = params.get("archived") === "1";
  const q = params.get("q") ?? "";
  const [search, setSearch] = useState(q);
  useEffect(() => {
    if (search === q) return;
    const id = window.setTimeout(() => update({ q: search.trim() || null }), 250);
    return () => window.clearTimeout(id);
  }, [search, q, update]);

  const projects = useAsync((s) => client.projects.list({ status: archived ? "all" : "active", sort: "name", limit: 100 }, s), [client, archived]);
  const result = useAsync(
    (s) =>
      client.components.parts(
        { q: q || undefined, project_id: projectId || undefined, include_archived: archived, sort, limit: PAGE_SIZE, offset: page * PAGE_SIZE },
        s,
      ),
    [client, q, projectId, archived, sort, page],
  );
  const data = result.data;
  const filtered = Boolean(q) || Boolean(projectId);

  return (
    <>
      <PageHeader
        title="Components"
        description="Parts placed on the current revision of every design you can access, grouped by value and footprint."
      />
      <div className="mb-3 flex flex-wrap items-center gap-2">
        <div className="relative min-w-56 flex-1">
          <Search className="pointer-events-none absolute top-1/2 left-2.5 size-3.5 -translate-y-1/2 text-subtle" aria-hidden="true" />
          <Input type="search" aria-label="Search components" placeholder="Value, footprint or reference (10k, 0603, U3)" className="pl-8" maxLength={100} value={search} onChange={(e) => setSearch(e.target.value)} />
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
        <Select aria-label="Sort by" className="w-auto" value={sort} onChange={(e) => update({ sort: e.target.value === "placements" ? null : e.target.value })}>
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
          title="Couldn't load components"
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
          title="Parts"
          meta={
            data ? (
              <>
                <Mono>{data.total}</Mono> distinct · <Mono>{data.placements}</Mono> placements · <Mono>{data.designs}</Mono> {data.designs === 1 ? "design" : "designs"}
              </>
            ) : undefined
          }
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
              {Array.from({ length: 8 }, (_, i) => (
                <Skeleton key={i} className="h-8 w-full" />
              ))}
            </div>
          ) : data.items.length === 0 ? (
            filtered ? (
              <EmptyState icon={<SearchX />} title="No matching components" description="Try a different value, footprint or reference." />
            ) : (
              <EmptyState icon={<Boxes />} title="No components yet" description="Components appear here once a KiCad board has been imported into one of your projects." />
            )
          ) : (
            <>
              <table className={cn("hidden w-full table-fixed text-[13px] md:table", result.loading && "opacity-60")}>
                <caption className="sr-only">Parts</caption>
                <colgroup>
                  <col className="w-[18%]" />
                  <col className="w-[30%]" />
                  <col className="w-[88px]" />
                  <col />
                  <col className="hidden w-[22%] lg:table-column" />
                </colgroup>
                <thead className="border-b border-border bg-surface-sunken text-left text-xs text-muted">
                  <tr>
                    <th scope="col" className="h-8 pl-4 pr-3 font-medium">Value</th>
                    <th scope="col" className="h-8 px-3 font-medium">Footprint</th>
                    <th scope="col" className="h-8 px-3 text-right font-medium">Placed</th>
                    <th scope="col" className="h-8 px-3 font-medium">References</th>
                    <th scope="col" className="hidden h-8 pl-3 pr-4 font-medium lg:table-cell">Designs</th>
                  </tr>
                </thead>
                <tbody>
                  {data.items.map((p) => (
                    <tr key={`${p.value ?? ""}|${p.footprint}`} className="border-b border-border align-top last:border-0 hover:bg-surface-hover">
                      <td className="py-2 pl-4 pr-3">
                        {p.value ? <Mono className="block truncate text-foreground" title={p.value}>{p.value}</Mono> : <span className="text-xs text-subtle">No value</span>}
                      </td>
                      <td className="px-3 py-2">
                        <Footprint id={p.footprint} />
                      </td>
                      <td className="px-3 py-2 text-right">
                        <Mono className="text-foreground">{p.placements}</Mono>
                        <span className="block text-xs text-subtle">
                          in <Mono>{p.design_count}</Mono>
                        </span>
                      </td>
                      <td className="px-3 py-2">
                        <Mono className="text-muted">
                          {p.references.join(", ")}
                          {p.references_truncated ? ", …" : ""}
                        </Mono>
                      </td>
                      <td className="hidden py-2 pl-3 pr-4 lg:table-cell">
                        <Designs part={p} />
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
              <ul className="divide-y divide-border md:hidden" aria-label="Parts">
                {data.items.map((p) => (
                  <li key={`${p.value ?? ""}|${p.footprint}`} className="space-y-1 px-4 py-2.5">
                    <div className="flex items-baseline gap-2">
                      <Mono className="min-w-0 flex-1 truncate text-sm text-foreground">{p.value ?? "No value"}</Mono>
                      <span className="shrink-0 text-xs text-subtle">
                        <Mono className="text-foreground">{p.placements}</Mono> placed in <Mono>{p.design_count}</Mono>
                      </span>
                    </div>
                    <Footprint id={p.footprint} />
                    <Designs part={p} />
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
