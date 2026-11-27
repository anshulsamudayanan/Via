"use client";

import {
  Badge,
  cn,
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuLabel,
  DropdownMenuSeparator,
  DropdownMenuTrigger,
  Kbd,
  SPRING,
  Tooltip,
} from "@via/ui";
import { ChevronsUpDown, LogOut, Moon, PanelLeftClose, PanelLeftOpen, Search, Settings, Sun } from "lucide-react";
import { m } from "motion/react";
import Link from "next/link";
import { usePathname, useRouter } from "next/navigation";
import type { ReactNode } from "react";

import { useSession } from "@/components/session";
import { ViaLogo } from "@/components/via-logo";
import { setTheme, useTheme } from "@/lib/use-theme";

import { useOpenCommandMenu } from "./command-menu";
import { isActive, NAV_GROUPS, type NavEntry } from "./nav";
import { StatusIndicator } from "./status-indicator";

function initials(name: string): string {
  return name
    .split(/\s+/)
    .filter(Boolean)
    .slice(0, 2)
    .map((p) => p[0]!.toUpperCase())
    .join("");
}

/** Shows a tooltip only when the sidebar is collapsed (the label is visible otherwise). */
function MaybeTooltip({ show, content, children }: { show: boolean; content: ReactNode; children: ReactNode }) {
  return show ? (
    <Tooltip content={content} side="right">
      {children}
    </Tooltip>
  ) : (
    <>{children}</>
  );
}

const itemBase =
  "relative isolate flex h-9 w-full items-center gap-2.5 rounded-xl px-2.5 text-[13.5px] whitespace-nowrap outline-none transition-colors duration-150 [&>svg]:size-[17px] [&>svg]:shrink-0";

function NavItem({ entry, collapsed, layoutGroup, onNavigate }: { entry: NavEntry; collapsed: boolean; layoutGroup: string; onNavigate?: () => void }) {
  const pathname = usePathname();
  const Icon = entry.icon;
  if (!entry.href) {
    return (
      <MaybeTooltip show content={entry.soon}>
        <span
          role="link"
          aria-disabled="true"
          aria-label={`${entry.label} (coming soon)`}
          tabIndex={collapsed ? 0 : -1}
          className={cn(itemBase, "cursor-default text-subtle", collapsed && "justify-center px-0")}
        >
          <Icon aria-hidden="true" />
          {collapsed ? null : (
            <>
              <span className="flex-1">{entry.label}</span>
              <Badge className="font-normal">Soon</Badge>
            </>
          )}
        </span>
      </MaybeTooltip>
    );
  }
  const active = isActive(pathname, entry.href);
  return (
    <MaybeTooltip show={collapsed} content={entry.label}>
      <Link
        href={entry.href}
        onClick={onNavigate}
        aria-current={active ? "page" : undefined}
        aria-label={collapsed ? entry.label : undefined}
        className={cn(
          itemBase,
          active ? "font-medium text-foreground" : "text-muted hover:bg-surface-hover hover:text-foreground",
          collapsed && "justify-center px-0",
        )}
      >
        {active ? (
          // The active item is a glass pill that slides between items (shared layoutId, spring).
          <m.span
            layoutId={`nav-pill-${layoutGroup}`}
            transition={SPRING}
            aria-hidden="true"
            className="absolute inset-0 -z-10 rounded-xl bg-[color-mix(in_oklab,var(--via-accent)_14%,var(--via-glass-regular))] shadow-[inset_0_1px_0_var(--via-glass-highlight),0_4px_14px_-6px_var(--via-accent-glow)] ring-1 ring-accent-border"
          />
        ) : null}
        <Icon aria-hidden="true" className={active ? "text-accent" : undefined} />
        {collapsed ? null : entry.label}
      </Link>
    </MaybeTooltip>
  );
}

function AccountRow({ collapsed }: { collapsed: boolean }) {
  const { me, signOut } = useSession();
  const router = useRouter();
  const theme = useTheme();
  const next = theme === "dark" ? "light" : "dark";
  const themeButton = (
    <button
      type="button"
      onClick={() => setTheme(next)}
      aria-label={`Switch to ${next} theme`}
      className="flex size-9 shrink-0 items-center justify-center rounded-full text-muted hover:bg-surface-hover hover:text-foreground [&>svg]:size-4"
    >
      {theme === "dark" ? <Sun aria-hidden="true" /> : <Moon aria-hidden="true" />}
    </button>
  );
  return (
    <div className={cn("flex gap-1 border-t border-border p-2.5", collapsed ? "flex-col items-center" : "items-center")}>
      <DropdownMenu>
        <DropdownMenuTrigger
          className={cn(
            "flex min-w-0 items-center gap-2 rounded-xl text-left outline-none hover:bg-surface-hover",
            collapsed ? "size-9 justify-center" : "h-11 flex-1 px-2",
          )}
          aria-label="Account menu"
        >
          <span className="flex size-7 shrink-0 items-center justify-center rounded-full bg-accent-soft text-[11px] font-semibold text-accent ring-1 ring-accent-border">
            {initials(me.user.display_name)}
          </span>
          {collapsed ? null : (
            <>
              <span className="min-w-0 flex-1 truncate text-[13px] text-foreground">{me.user.display_name}</span>
              <ChevronsUpDown className="size-3.5 shrink-0 text-subtle" aria-hidden="true" />
            </>
          )}
        </DropdownMenuTrigger>
        <DropdownMenuContent align="start" side="top" className="min-w-56">
          <DropdownMenuLabel>
            <span className="block text-foreground">{me.user.display_name}</span>
            <span className="block break-all">{me.user.email}</span>
          </DropdownMenuLabel>
          <DropdownMenuSeparator />
          <DropdownMenuItem onSelect={() => router.push("/settings")}>
            <Settings /> Account settings
          </DropdownMenuItem>
          <DropdownMenuItem onSelect={() => setTheme(next)}>
            {theme === "dark" ? <Sun /> : <Moon />} {theme === "dark" ? "Light theme" : "Dark theme"}
          </DropdownMenuItem>
          <DropdownMenuSeparator />
          <DropdownMenuItem onSelect={() => void signOut()}>
            <LogOut /> Sign out
          </DropdownMenuItem>
        </DropdownMenuContent>
      </DropdownMenu>
      <MaybeTooltip show={collapsed} content={`Switch to ${next} theme`}>
        {themeButton}
      </MaybeTooltip>
    </div>
  );
}

interface SidebarProps {
  collapsed?: boolean;
  onToggleCollapsed?: () => void;
  /** Called after a navigation (the mobile sheet closes itself). */
  onNavigate?: () => void;
  layoutGroup: string;
}

/** Sidebar body, shared by the desktop rail and the mobile sheet. */
export function SidebarContent({ collapsed = false, onToggleCollapsed, onNavigate, layoutGroup }: SidebarProps) {
  const openSearch = useOpenCommandMenu();
  return (
    <div className="flex h-full flex-col">
      <div className={cn("flex h-14 shrink-0 items-center gap-2 px-4", collapsed && "justify-center px-0")}>
        <Link href="/dashboard" onClick={onNavigate} aria-label="VIA dashboard" className="rounded-sm">
          <ViaLogo compact={collapsed} />
        </Link>
        {onToggleCollapsed && !collapsed ? (
          <button
            type="button"
            onClick={onToggleCollapsed}
            aria-label="Collapse sidebar"
            aria-expanded="true"
            title="Collapse sidebar ([)"
            className="ml-auto flex size-8 items-center justify-center rounded-full text-subtle hover:bg-surface-hover hover:text-foreground [&>svg]:size-4"
          >
            <PanelLeftClose aria-hidden="true" />
          </button>
        ) : null}
      </div>

      <div className={cn("px-2.5 pb-2", collapsed && "flex flex-col items-center gap-1")}>
        {collapsed && onToggleCollapsed ? (
          <Tooltip content="Expand sidebar ([)" side="right">
            <button
              type="button"
              onClick={onToggleCollapsed}
              aria-label="Expand sidebar"
              aria-expanded="false"
              className="flex size-9 items-center justify-center rounded-full text-subtle hover:bg-surface-hover hover:text-foreground [&>svg]:size-4"
            >
              <PanelLeftOpen aria-hidden="true" />
            </button>
          </Tooltip>
        ) : null}
        <MaybeTooltip show={collapsed} content="Search (⌘K)">
          <button
            type="button"
            onClick={() => {
              onNavigate?.();
              openSearch();
            }}
            aria-label="Search"
            aria-keyshortcuts="Meta+K Control+K"
            className={cn(
              "flex h-9 items-center gap-2 rounded-full border border-border bg-surface-sunken text-[13px] text-subtle shadow-[inset_0_1px_0_var(--via-glass-highlight)] hover:border-border-strong hover:text-muted [&>svg]:size-4",
              collapsed ? "w-9 justify-center border-transparent bg-transparent shadow-none" : "w-full px-3",
            )}
          >
            <Search aria-hidden="true" />
            {collapsed ? null : (
              <>
                <span className="flex-1 text-left">Search…</span>
                <Kbd className="hidden md:inline-flex">⌘K</Kbd>
              </>
            )}
          </button>
        </MaybeTooltip>
      </div>

      <nav aria-label="Main" className="min-h-0 flex-1 overflow-y-auto px-2.5 pb-2">
        {NAV_GROUPS.map((group) => (
          <div key={group.label} className="pt-3 first:pt-1">
            {collapsed ? (
              <div className="mx-auto mb-1 h-px w-5 bg-border" aria-hidden="true" />
            ) : (
              <h2 id={`${layoutGroup}-${group.label}`} className="px-2.5 pb-1 text-[11px] font-semibold tracking-tight text-subtle">
                {group.label}
              </h2>
            )}
            <ul aria-labelledby={collapsed ? undefined : `${layoutGroup}-${group.label}`} aria-label={collapsed ? group.label : undefined} className="space-y-px">
              {group.items.map((entry) => (
                <li key={entry.label}>
                  <NavItem entry={entry} collapsed={collapsed} layoutGroup={layoutGroup} onNavigate={onNavigate} />
                </li>
              ))}
            </ul>
          </div>
        ))}
      </nav>

      <div className={cn("px-2.5 pb-1.5", collapsed && "flex justify-center")}>
        <StatusIndicator collapsed={collapsed} onNavigate={onNavigate} />
      </div>
      <AccountRow collapsed={collapsed} />
    </div>
  );
}
