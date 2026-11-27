"use client";

import type { Project, ProjectSort } from "@via/types";
import { Button, cn, EmptyState, ErrorState, Kbd, Mono, Panel, SegmentedControl, Skeleton, SPRING_SOFT } from "@via/ui";
import { ArrowDown, ArrowRight, ArrowUp, Building2, FolderKanban, LayoutGrid, Lock, Rows3, Search } from "lucide-react";
import { AnimatePresence, m } from "motion/react";
import Link from "next/link";
import { type KeyboardEvent, useEffect, useRef, useState, useSyncExternalStore } from "react";

import { useApi } from "@/components/api-context";
import { RoleBadge, VisibilityBadge } from "@/components/projects/badges";
import { errorMessage } from "@/lib/errors";
import { formatDateTime, relativeTime } from "@/lib/format";
import { useAsync } from "@/lib/use-async";

import { LastAnalyzed, LastRevision, SeverityCounts } from "./project-status";

const LIMIT = 8;
const SORT_LABEL: Record<ProjectSort, string> = { updated: "Last updated", created: "Newest", name: "Name" };

// ------------------------------------------------------------------ view choice (table / cards)

type View = "table" | "cards";
const VIEW_KEY = "via-dashboard-view";
const viewListeners = new Set<() => void>();
function readView(): View {
  try {
    return localStorage.getItem(VIEW_KEY) === "cards" ? "cards" : "table";
  } catch {
    return "table";
  }
}
function setView(v: View) {
  try {
    localStorage.setItem(VIEW_KEY, v);
  } catch {
    // Storage unavailable: the choice lasts until reload.
  }
  viewListeners.forEach((l) => l());
}
function useView(): View {
  return useSyncExternalStore(
    (fn) => {
      viewListeners.add(fn);
      return () => void viewListeners.delete(fn);
    },
    readView,
    () => "table",
  );
}

function useDebounced<T>(value: T, ms: number): T {
  const [v, setV] = useState(value);
  useEffect(() => {
    const t = setTimeout(() => setV(value), ms);
    return () => clearTimeout(t);
  }, [value, ms]);
  return v;
}

/** Up/Down (and Home/End) move between project links, so the list is usable from the keyboard alone. */
function onListKeyDown(e: KeyboardEvent<HTMLElement>) {
  if (!["ArrowDown", "ArrowUp", "Home", "End"].includes(e.key)) return;
  // Only visible links: the table and the phone cards share one container.
  const links = Array.from(e.currentTarget.querySelectorAll<HTMLAnchorElement>("a[data-project-link]")).filter((a) => a.getClientRects().length > 0);
  if (!links.length) return;
  const i = links.indexOf(document.activeElement as HTMLAnchorElement);
  const next = e.key === "Home" ? 0 : e.key === "End" ? links.length - 1 : e.key === "ArrowDown" ? Math.min(i + 1, links.length - 1) : Math.max(i - 1, 0);
  e.preventDefault();
  links[next]?.focus();
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

function ViewToggle({ view }: { view: View }) {
  return (
    <SegmentedControl
      aria-label="Project view"
      iconOnly
      value={view}
      onChange={setView}
      segments={[
        { value: "table", label: "Table", icon: <Rows3 aria-hidden="true" /> },
        { value: "cards", label: "Cards", icon: <LayoutGrid aria-hidden="true" /> },
      ]}
    />
  );
}

/** Compact access line for table rows: private or organization, plus your role when you aren't the owner. */
function AccessLabel({ project: p }: { project: Project }) {
  const Icon = p.visibility === "private" ? Lock : Building2;
  return (
    <span
      className="inline-flex shrink-0 items-center gap-1 text-muted"
      title={p.visibility === "private" ? "Only the owner and invited members can see this project." : "Members of the owning organization can view this project."}
    >
      <Icon className="size-3" aria-hidden="true" />
      {p.visibility === "private" ? "Private" : "Organization"}
      {p.my_role !== "owner" ? <span className="text-subtle">· {p.my_role === "editor" ? "Editor" : "Viewer"}</span> : null}
    </span>
  );
}

function Updated({ at }: { at: string }) {
  return (
    <time dateTime={at} title={formatDateTime(at)} className="whitespace-nowrap text-xs text-subtle tabular-nums">
      {relativeTime(at)}
    </time>
  );
}

function ProjectTable({ items, sort, onSort, dim }: { items: Project[]; sort: ProjectSort; onSort: (s: ProjectSort) => void; dim: boolean }) {
  return (
    <table className={cn("w-full table-fixed text-[13px] transition-opacity", dim && "opacity-60")}>
      <colgroup>
        <col />
        <col className="w-[19%]" />
        <col className="hidden w-[104px] lg:table-column" />
        <col className="w-[272px]" />
        <col className="hidden w-[112px] 2xl:table-column" />
      </colgroup>
      <thead className="border-b border-border bg-surface-sunken/60 text-left text-xs text-muted">
        <tr>
          <SortHeader label="Project" sort="name" current={sort} onSort={onSort} className="pl-5" />
          <th scope="col" className="h-8 px-3 font-medium">Last revision</th>
          <th scope="col" className="hidden h-8 px-3 font-medium lg:table-cell">Analysed</th>
          <th scope="col" className="h-8 px-3 font-medium">Findings</th>
          <SortHeader label="Updated" sort="updated" current={sort} onSort={onSort} className="hidden pr-4 text-right 2xl:table-cell" />
        </tr>
      </thead>
      <tbody>
        {items.map((p) => (
          <m.tr
            key={p.id}
            layout="position"
            transition={SPRING_SOFT}
            initial={{ opacity: 0 }}
            animate={{ opacity: 1 }}
            className="border-b border-border transition-colors duration-150 last:border-0 hover:bg-surface-hover"
          >
            <td className="py-2.5 pl-5 pr-3">
              <Link data-project-link href={`/projects/${p.id}`} className="block truncate rounded-sm font-medium text-foreground hover:underline">
                {p.name}
              </Link>
              <span className="flex min-w-0 items-center gap-1.5 text-xs text-subtle">
                <AccessLabel project={p} />
                <span aria-hidden="true">·</span>
                <span className="truncate">{p.description || "No description"}</span>
              </span>
            </td>
            <td className="min-w-0 px-3">
              <LastRevision projectId={p.id} value={p.latest_import} />
            </td>
            <td className="hidden px-3 lg:table-cell">
              <LastAnalyzed value={p.latest_analysis} />
            </td>
            <td className="px-3">
              <SeverityCounts projectId={p.id} value={p.latest_analysis} />
            </td>
            <td className="hidden pl-3 pr-4 text-right 2xl:table-cell">
              <Updated at={p.updated_at} />
            </td>
          </m.tr>
        ))}
      </tbody>
    </table>
  );
}

function ProjectCards({ items, dim, forceCompact }: { items: Project[]; dim: boolean; forceCompact?: boolean }) {
  return (
    <ul aria-label="Projects" className={cn("grid gap-3 p-3 transition-opacity", !forceCompact && "sm:grid-cols-2", dim && "opacity-60")}>
      <AnimatePresence initial={false} mode="popLayout">
      {items.map((p) => (
        <m.li
          key={p.id}
          layout
          transition={SPRING_SOFT}
          initial={{ opacity: 0, scale: 0.97 }}
          animate={{ opacity: 1, scale: 1 }}
          exit={{ opacity: 0, scale: 0.97 }}
          whileHover={{ y: -2 }}
          className="group/card relative flex min-w-0 flex-col gap-3 rounded-[20px] border border-border bg-surface px-4 py-3.5 shadow-[inset_0_1px_0_var(--via-glass-highlight)] transition-colors duration-150 hover:border-border-strong hover:bg-surface-hover"
        >
          <div className="flex min-w-0 items-start gap-2">
            <div className="min-w-0 flex-1">
              <Link
                data-project-link
                href={`/projects/${p.id}`}
                className="block truncate rounded-sm text-sm font-medium text-foreground after:absolute after:inset-0 after:content-[''] hover:underline"
              >
                {p.name}
              </Link>
              <p className="truncate text-xs text-subtle">{p.description || "No description"}</p>
            </div>
            <Updated at={p.updated_at} />
          </div>
          {/* Inner links sit above the card-wide link. */}
          <dl className="relative grid grid-cols-[auto_minmax(0,1fr)] items-center gap-x-3 gap-y-1.5 text-xs">
            <dt className="text-subtle">Revision</dt>
            <dd className="min-w-0">
              <LastRevision projectId={p.id} value={p.latest_import} />
            </dd>
            <dt className="text-subtle">Analysed</dt>
            <dd>
              <LastAnalyzed value={p.latest_analysis} />
            </dd>
            <dt className="text-subtle">Findings</dt>
            <dd className="min-w-0">
              <SeverityCounts projectId={p.id} value={p.latest_analysis} />
            </dd>
          </dl>
          <div className="relative flex flex-wrap items-center gap-1">
            <VisibilityBadge visibility={p.visibility} />
            <RoleBadge role={p.my_role} />
            <span className="ml-auto text-xs text-subtle">
              <Mono>{p.design_count}</Mono> {p.design_count === 1 ? "design" : "designs"}
            </span>
          </div>
        </m.li>
      ))}
      </AnimatePresence>
    </ul>
  );
}

function LoadingRows({ view }: { view: View }) {
  // Same height as the loaded content's first rows, so nothing jumps when data arrives.
  return view === "table" ? (
    <div aria-busy="true" aria-label="Loading projects" className="divide-y divide-border">
      <div className="h-8 bg-surface-sunken" />
      {Array.from({ length: 4 }, (_, i) => (
        <div key={i} className="flex h-[53px] items-center gap-4 px-4">
          <div className="flex-1 space-y-1.5">
            <Skeleton className="h-3.5 w-40" />
            <Skeleton className="h-3 w-56 max-w-full" />
          </div>
          <Skeleton className="hidden h-3.5 w-28 md:block" />
          <Skeleton className="h-4 w-20" />
        </div>
      ))}
    </div>
  ) : (
    <div aria-busy="true" aria-label="Loading projects" className="grid gap-3 p-3 sm:grid-cols-2">
      {Array.from({ length: 4 }, (_, i) => (
        <div key={i} className="h-[160px] space-y-2 rounded-[20px] border border-border bg-surface px-4 py-3.5">
          <Skeleton className="h-4 w-36" />
          <Skeleton className="h-3 w-48 max-w-full" />
          <Skeleton className="mt-4 h-3 w-40" />
          <Skeleton className="h-3 w-24" />
        </div>
      ))}
    </div>
  );
}

/** Active projects: last revision, last analysis, findings by severity and access. Server-side search and sort. */
export function ProjectsPanel() {
  const client = useApi();
  const view = useView();
  const [query, setQuery] = useState("");
  const [sort, setSort] = useState<ProjectSort>("updated");
  const searchRef = useRef<HTMLInputElement>(null);
  const q = useDebounced(query.trim(), 250);
  const page = useAsync((s) => client.projects.list({ q: q || undefined, status: "active", sort, limit: LIMIT }, s), [client, q, sort]);
  const items = page.data?.items ?? [];

  // "/" focuses the filter, as in most engineering tools.
  useEffect(() => {
    function onKey(e: globalThis.KeyboardEvent) {
      const el = e.target as HTMLElement | null;
      if (e.key !== "/" || e.metaKey || e.ctrlKey || e.altKey) return;
      if (el && (el.isContentEditable || ["INPUT", "TEXTAREA", "SELECT"].includes(el.tagName))) return;
      e.preventDefault();
      searchRef.current?.focus();
    }
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, []);

  return (
    <Panel
      title="Projects"
      meta={page.data ? `${page.data.total} active` : undefined}
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
      <div className="flex flex-wrap items-center gap-2 border-b border-border px-4 py-2.5">
        <label className="relative min-w-0 basis-full sm:max-w-72 sm:flex-1 sm:basis-auto">
          <span className="sr-only">Filter projects</span>
          <Search className="pointer-events-none absolute left-3 top-1/2 size-3.5 -translate-y-1/2 text-subtle" aria-hidden="true" />
          <input
            ref={searchRef}
            type="search"
            value={query}
            onChange={(e) => setQuery(e.target.value)}
            onKeyDown={(e) => {
              if (e.key === "Escape" && query) {
                e.preventDefault();
                setQuery("");
              }
            }}
            placeholder="Filter projects"
            aria-keyshortcuts="/"
            className="h-8 w-full rounded-full border border-border bg-surface-sunken pl-8 pr-9 text-xs text-foreground shadow-[inset_0_1px_0_var(--via-glass-highlight)] outline-none placeholder:text-subtle focus:border-accent-border"
          />
          <Kbd className="pointer-events-none absolute right-2 top-1/2 hidden -translate-y-1/2 sm:inline-flex">/</Kbd>
        </label>
        <label className="ml-auto flex items-center gap-1.5 text-xs text-subtle">
          <span className="sr-only sm:not-sr-only">Sort</span>
          <select
            value={sort}
            onChange={(e) => setSort(e.target.value as ProjectSort)}
            className="h-8 cursor-pointer rounded-full border border-border bg-surface-sunken px-3 text-xs text-foreground outline-none focus:border-accent-border"
          >
            {(Object.keys(SORT_LABEL) as ProjectSort[]).map((s) => (
              <option key={s} value={s}>
                {SORT_LABEL[s]}
              </option>
            ))}
          </select>
        </label>
        <ViewToggle view={view} />
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
        <LoadingRows view={view} />
      ) : items.length === 0 ? (
        <EmptyState
          icon={<FolderKanban />}
          title={q ? `No active projects match “${q}”` : "No active projects"}
          description={q ? "Try another name, or search archived projects on the Projects page." : "Archived projects are listed on the Projects page."}
        />
      ) : (
        <div onKeyDown={onListKeyDown}>
          {view === "table" ? (
            <>
              <div className="hidden md:block">
                <ProjectTable items={items} sort={sort} onSort={setSort} dim={page.loading} />
              </div>
              {/* Phones always get cards: a five-column table doesn't fit. */}
              <div className="md:hidden">
                <ProjectCards items={items} dim={page.loading} forceCompact />
              </div>
            </>
          ) : (
            <ProjectCards items={items} dim={page.loading} />
          )}
        </div>
      )}
    </Panel>
  );
}
