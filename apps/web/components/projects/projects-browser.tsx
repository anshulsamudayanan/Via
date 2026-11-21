"use client";

import type { ProjectSort, ProjectStatusFilter } from "@via/types";
import { Button, Card, EmptyState, ErrorState, Input, Select, Skeleton, Table, TBody, TD, TH, THead, TR } from "@via/ui";
import { ChevronLeft, ChevronRight, FolderPlus, Search, SearchX } from "lucide-react";
import Link from "next/link";
import { usePathname, useRouter, useSearchParams } from "next/navigation";
import { useEffect, useState } from "react";

import { useApi } from "@/components/api-context";
import { PageHeader } from "@/components/app-shell";
import { ArchivedBadge, RoleBadge, VisibilityBadge } from "@/components/projects/badges";
import { NewProjectDialog } from "@/components/projects/new-project-dialog";
import { errorMessage } from "@/lib/errors";
import { formatDateTime, relativeTime } from "@/lib/format";
import { useAsync } from "@/lib/use-async";

const PAGE_SIZE = 25;
const STATUSES: ProjectStatusFilter[] = ["active", "archived", "all"];
const SORTS: ProjectSort[] = ["updated", "created", "name"];

function pick<T extends string>(value: string | null, allowed: T[], fallback: T): T {
  return allowed.includes(value as T) ? (value as T) : fallback;
}

export function ProjectsBrowser() {
  const client = useApi();
  const router = useRouter();
  const pathname = usePathname();
  const params = useSearchParams();
  const status = pick(params.get("status"), STATUSES, "active");
  const sort = pick(params.get("sort"), SORTS, "updated");
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

  // Debounce typing into the URL (which triggers the fetch).
  useEffect(() => {
    if (search === q) return;
    const id = window.setTimeout(() => update({ q: search.trim() || null }), 250);
    return () => window.clearTimeout(id);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [search]);

  const result = useAsync(
    (signal) => client.projects.list({ q: q || undefined, status, sort, limit: PAGE_SIZE, offset: page * PAGE_SIZE }, signal),
    [client, q, status, sort, page],
  );
  const data = result.data;
  const filtered = Boolean(q) || status !== "active";

  return (
    <>
      <PageHeader
        title="Projects"
        description="Projects you own or that are shared with you."
        actions={<NewProjectDialog onCreated={(p) => router.push(`/projects/${p.id}`)} />}
      />
      <div className="mb-3 flex flex-wrap items-center gap-2">
        <div className="relative min-w-56 flex-1">
          <Search className="pointer-events-none absolute top-1/2 left-2.5 size-3.5 -translate-y-1/2 text-subtle" aria-hidden="true" />
          <Input
            type="search"
            aria-label="Search projects"
            placeholder="Search by name or description"
            className="pl-8"
            maxLength={100}
            value={search}
            onChange={(e) => setSearch(e.target.value)}
          />
        </div>
        <Select aria-label="Status" className="w-auto" value={status} onChange={(e) => update({ status: e.target.value === "active" ? null : e.target.value })}>
          <option value="active">Active</option>
          <option value="archived">Archived</option>
          <option value="all">All</option>
        </Select>
        <Select aria-label="Sort by" className="w-auto" value={sort} onChange={(e) => update({ sort: e.target.value === "updated" ? null : e.target.value })}>
          <option value="updated">Recently updated</option>
          <option value="created">Recently created</option>
          <option value="name">Name</option>
        </Select>
      </div>

      {result.error ? (
        <ErrorState
          title="Couldn't load projects"
          description={errorMessage(result.error)}
          action={
            <Button size="sm" onClick={result.reload}>
              Retry
            </Button>
          }
        />
      ) : (
        <Card aria-busy={result.loading}>
          {!data ? (
            <div className="space-y-2 p-4">
              {Array.from({ length: 5 }, (_, i) => (
                <Skeleton key={i} className="h-8 w-full" />
              ))}
            </div>
          ) : data.items.length === 0 ? (
            filtered ? (
              <EmptyState icon={<SearchX />} title="No matching projects" description="Try a different search or filter." />
            ) : (
              <EmptyState
                icon={<FolderPlus />}
                title="No projects yet"
                description="Create a project to start organizing your PCB designs."
                action={<NewProjectDialog onCreated={(p) => router.push(`/projects/${p.id}`)} />}
              />
            )
          ) : (
            <>
              <Table>
                <caption className="sr-only">Projects</caption>
                <THead>
                  <tr>
                    <TH>Name</TH>
                    <TH className="hidden md:table-cell">Organization</TH>
                    <TH>Access</TH>
                    <TH className="hidden text-right sm:table-cell">Designs</TH>
                    <TH className="text-right">Updated</TH>
                  </tr>
                </THead>
                <TBody>
                  {data.items.map((p) => (
                    <TR key={p.id} className="hover:bg-surface-hover">
                      <TD className="max-w-0 w-1/2">
                        <Link href={`/projects/${p.id}`} className="block truncate font-medium text-foreground hover:underline">
                          {p.name}
                        </Link>
                        <span className="block truncate text-xs text-muted">{p.description || "No description"}</span>
                      </TD>
                      <TD className="hidden text-muted md:table-cell">{p.organization.is_personal ? "Personal" : p.organization.name}</TD>
                      <TD>
                        <div className="flex flex-wrap items-center gap-1">
                          <RoleBadge role={p.my_role} />
                          <VisibilityBadge visibility={p.visibility} />
                          <ArchivedBadge project={p} />
                        </div>
                      </TD>
                      <TD className="hidden text-right font-mono text-xs tabular-nums sm:table-cell">{p.design_count}</TD>
                      <TD className="text-right text-xs whitespace-nowrap text-muted" title={formatDateTime(p.updated_at)}>
                        {relativeTime(p.updated_at)}
                      </TD>
                    </TR>
                  ))}
                </TBody>
              </Table>
              <div className="flex items-center justify-between border-t border-border px-3 py-2 text-xs text-muted">
                <span>
                  {page * PAGE_SIZE + 1}–{page * PAGE_SIZE + data.items.length} of {data.total}
                </span>
                <div className="flex gap-1">
                  <Button size="sm" variant="ghost" disabled={page === 0} onClick={() => update({ page: page - 1 ? String(page - 1) : null })} aria-label="Previous page">
                    <ChevronLeft />
                  </Button>
                  <Button
                    size="sm"
                    variant="ghost"
                    disabled={(page + 1) * PAGE_SIZE >= data.total}
                    onClick={() => update({ page: String(page + 1) })}
                    aria-label="Next page"
                  >
                    <ChevronRight />
                  </Button>
                </div>
              </div>
            </>
          )}
        </Card>
      )}
    </>
  );
}
