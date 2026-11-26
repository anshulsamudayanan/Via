"use client";

import type { Project } from "@via/types";
import { Dialog, DialogContent, Kbd, Mono, Spinner } from "@via/ui";
import { CornerDownLeft, FolderKanban, Moon, Search } from "lucide-react";
import { useRouter } from "next/navigation";
import { createContext, type ReactNode, useCallback, useContext, useEffect, useId, useMemo, useState } from "react";

import { useApi } from "@/components/api-context";
import { setTheme, useTheme } from "@/lib/use-theme";

import { NAV_LINKS } from "./nav";

const CommandMenuContext = createContext<() => void>(() => {});

/** Opens the global search (also bound to ⌘K / Ctrl+K). */
export function useOpenCommandMenu() {
  return useContext(CommandMenuContext);
}

export function CommandMenuProvider({ children }: { children: ReactNode }) {
  const [open, setOpen] = useState(false);
  const show = useCallback(() => setOpen(true), []);
  useEffect(() => {
    function onKey(e: KeyboardEvent) {
      if ((e.metaKey || e.ctrlKey) && e.key.toLowerCase() === "k") {
        e.preventDefault();
        setOpen((o) => !o);
      }
    }
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, []);
  return (
    <CommandMenuContext.Provider value={show}>
      {children}
      <Dialog open={open} onOpenChange={setOpen}>
        {open ? <CommandMenu onDone={() => setOpen(false)} /> : null}
      </Dialog>
    </CommandMenuContext.Provider>
  );
}

interface Item {
  id: string;
  group: "Projects" | "Pages" | "Actions";
  label: string;
  hint?: ReactNode;
  icon: ReactNode;
  run: () => void;
}

function useProjectSearch(query: string) {
  const client = useApi();
  const [state, setState] = useState<{ q: string; items: Project[]; error: boolean } | null>(null);
  useEffect(() => {
    const ctrl = new AbortController();
    const t = setTimeout(() => {
      client.projects
        .list({ q: query.trim() || undefined, status: "all", sort: "updated", limit: 6 }, ctrl.signal)
        .then((page) => setState({ q: query, items: page.items, error: false }))
        .catch((err: unknown) => {
          if (!ctrl.signal.aborted) setState({ q: query, items: [], error: Boolean(err) });
        });
    }, 180);
    return () => {
      clearTimeout(t);
      ctrl.abort();
    };
  }, [client, query]);
  return { items: state?.items ?? [], loading: state?.q !== query, error: state?.error ?? false };
}

function CommandMenu({ onDone }: { onDone: () => void }) {
  const router = useRouter();
  const theme = useTheme();
  const listId = useId();
  const [query, setQuery] = useState("");
  const [active, setActive] = useState(0);
  const projects = useProjectSearch(query);

  const items = useMemo<Item[]>(() => {
    const q = query.trim().toLowerCase();
    const go = (href: string) => () => {
      onDone();
      router.push(href);
    };
    const nextTheme = theme === "dark" ? "light" : "dark";
    return [
      ...projects.items.map((p) => ({
        id: `p-${p.id}`,
        group: "Projects" as const,
        label: p.name,
        hint: (
          <Mono className="text-subtle">
            {p.design_count} {p.design_count === 1 ? "design" : "designs"}
            {p.archived_at ? " · archived" : ""}
          </Mono>
        ),
        icon: <FolderKanban />,
        run: go(`/projects/${p.id}`),
      })),
      ...NAV_LINKS.filter((n) => !q || n.label.toLowerCase().includes(q)).map((n) => ({
        id: `n-${n.href}`,
        group: "Pages" as const,
        label: n.label,
        icon: <n.icon />,
        run: go(n.href),
      })),
      ...(!q || "theme switch light dark".includes(q) || `switch to ${nextTheme} theme`.includes(q)
        ? [
            {
              id: "a-theme",
              group: "Actions" as const,
              label: `Switch to ${nextTheme} theme`,
              icon: <Moon />,
              run: () => {
                setTheme(nextTheme);
                onDone();
              },
            },
          ]
        : []),
    ];
  }, [projects.items, query, theme, router, onDone]);

  const current = Math.min(active, Math.max(items.length - 1, 0));

  function onKeyDown(e: React.KeyboardEvent) {
    if (e.key === "ArrowDown" || e.key === "ArrowUp") {
      e.preventDefault();
      if (items.length) setActive((current + (e.key === "ArrowDown" ? 1 : items.length - 1)) % items.length);
    } else if (e.key === "Enter") {
      e.preventDefault();
      items[current]?.run();
    }
  }

  let lastGroup = "";
  return (
    <DialogContent bare title="Search" className="top-[14vh] max-w-xl">
      <div className="flex items-center gap-2 border-b border-border px-3">
        <Search className="size-4 text-subtle" aria-hidden="true" />
        <input
          autoFocus
          role="combobox"
          aria-expanded="true"
          aria-controls={listId}
          aria-activedescendant={items[current] ? `${listId}-${items[current].id}` : undefined}
          aria-label="Search projects and pages"
          placeholder="Search projects, pages and actions…"
          value={query}
          onChange={(e) => {
            setQuery(e.target.value);
            setActive(0);
          }}
          onKeyDown={onKeyDown}
          className="h-11 min-w-0 flex-1 bg-transparent text-sm text-foreground outline-none placeholder:text-subtle"
        />
        {projects.loading ? <Spinner label="Searching" /> : null}
      </div>
      <ul id={listId} role="listbox" aria-label="Results" className="max-h-[50vh] overflow-y-auto p-1">
        {items.length === 0 && !projects.loading ? (
          <li className="px-3 py-6 text-center text-sm text-muted">
            {projects.error ? "Couldn't search projects. Check your connection and try again." : `No matches for “${query}”.`}
          </li>
        ) : null}
        {items.map((item, i) => {
          const header = item.group !== lastGroup ? item.group : null;
          lastGroup = item.group;
          return (
            <li key={item.id} role="presentation">
              {header ? <div className="px-2 pb-1 pt-2 text-[11px] font-medium uppercase tracking-[0.06em] text-subtle">{header}</div> : null}
              <div
                id={`${listId}-${item.id}`}
                role="option"
                aria-selected={i === current}
                onMouseMove={() => setActive(i)}
                onClick={item.run}
                className="flex h-9 cursor-pointer items-center gap-2.5 rounded-md px-2 text-sm text-foreground aria-selected:bg-accent-soft [&>svg]:size-4 [&>svg]:shrink-0 [&>svg]:text-subtle"
              >
                {item.icon}
                <span className="min-w-0 flex-1 truncate">{item.label}</span>
                {item.hint}
                {i === current ? <CornerDownLeft className="size-3.5 text-subtle" aria-hidden="true" /> : null}
              </div>
            </li>
          );
        })}
      </ul>
      <div className="flex items-center gap-3 border-t border-border px-3 py-2 text-[11px] text-subtle">
        <span className="flex items-center gap-1">
          <Kbd>↑</Kbd>
          <Kbd>↓</Kbd> navigate
        </span>
        <span className="flex items-center gap-1">
          <Kbd>↵</Kbd> open
        </span>
        <span className="flex items-center gap-1">
          <Kbd>esc</Kbd> close
        </span>
      </div>
    </DialogContent>
  );
}
