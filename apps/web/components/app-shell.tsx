"use client";

import {
  cn,
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuLabel,
  DropdownMenuSeparator,
  DropdownMenuTrigger,
} from "@via/ui";
import { Activity, ChevronsUpDown, FolderKanban, LayoutDashboard, LogOut, Settings } from "lucide-react";
import Link from "next/link";
import { usePathname, useRouter } from "next/navigation";
import type { ReactNode } from "react";

import { useSession } from "@/components/session";
import { ThemeToggle } from "@/components/theme-toggle";
import { ViaLogo } from "@/components/via-logo";

const NAV = [
  { href: "/dashboard", label: "Dashboard", icon: LayoutDashboard },
  { href: "/projects", label: "Projects", icon: FolderKanban },
  { href: "/activity", label: "Activity", icon: Activity },
  { href: "/settings", label: "Settings", icon: Settings },
];

function initials(name: string): string {
  return name
    .split(/\s+/)
    .filter(Boolean)
    .slice(0, 2)
    .map((p) => p[0]!.toUpperCase())
    .join("");
}

function UserMenu() {
  const { me, signOut } = useSession();
  const router = useRouter();
  return (
    <DropdownMenu>
      <DropdownMenuTrigger
        className="flex w-full items-center gap-2 rounded-md px-2 py-1.5 text-left hover:bg-surface-hover"
        aria-label="Account menu"
      >
        <span className="flex size-6 shrink-0 items-center justify-center rounded-full bg-accent-soft text-[11px] font-semibold text-accent">
          {initials(me.user.display_name)}
        </span>
        <span className="min-w-0 flex-1">
          <span className="block truncate text-sm text-foreground">{me.user.display_name}</span>
          <span className="block truncate text-xs text-muted">{me.user.email}</span>
        </span>
        <ChevronsUpDown className="size-3.5 text-subtle" aria-hidden="true" />
      </DropdownMenuTrigger>
      <DropdownMenuContent align="start" side="top">
        <DropdownMenuLabel>Signed in as {me.user.email}</DropdownMenuLabel>
        <DropdownMenuSeparator />
        <DropdownMenuItem onSelect={() => router.push("/settings")}>
          <Settings /> Account settings
        </DropdownMenuItem>
        <DropdownMenuItem onSelect={() => void signOut()}>
          <LogOut /> Sign out
        </DropdownMenuItem>
      </DropdownMenuContent>
    </DropdownMenu>
  );
}

export function AppShell({ children }: { children: ReactNode }) {
  const pathname = usePathname();
  const isActive = (href: string) => pathname === href || pathname.startsWith(`${href}/`);

  return (
    <div className="flex min-h-dvh flex-col md:flex-row">
      <aside className="flex shrink-0 flex-col border-b border-border bg-surface md:sticky md:top-0 md:h-dvh md:w-56 md:border-r md:border-b-0">
        <div className="flex h-12 items-center justify-between px-3">
          <Link href="/dashboard" aria-label="VIA dashboard" className="rounded-sm">
            <ViaLogo />
          </Link>
          <ThemeToggle />
        </div>
        <nav aria-label="Main" className="flex gap-0.5 overflow-x-auto px-2 pb-2 md:flex-1 md:flex-col md:pb-0">
          {NAV.map(({ href, label, icon: Icon }) => (
            <Link
              key={href}
              href={href}
              aria-current={isActive(href) ? "page" : undefined}
              className={cn(
                "flex items-center gap-2 rounded-md px-2 py-1.5 text-sm whitespace-nowrap transition-colors",
                isActive(href)
                  ? "bg-surface-hover font-medium text-foreground"
                  : "text-muted hover:bg-surface-hover hover:text-foreground",
              )}
            >
              <Icon className="size-4" aria-hidden="true" />
              {label}
            </Link>
          ))}
        </nav>
        <div className="hidden border-t border-border p-2 md:block">
          <UserMenu />
        </div>
      </aside>
      <main id="main" className="min-w-0 flex-1">
        <div className="mx-auto max-w-6xl px-4 py-6 md:px-6">{children}</div>
      </main>
    </div>
  );
}

/** Consistent page heading with optional actions on the right. */
export function PageHeader({ title, description, actions }: { title: ReactNode; description?: ReactNode; actions?: ReactNode }) {
  return (
    <div className="mb-5 flex flex-wrap items-start justify-between gap-3">
      <div className="min-w-0 space-y-0.5">
        <h1 className="truncate text-lg font-semibold tracking-tight">{title}</h1>
        {description ? <div className="text-sm text-muted">{description}</div> : null}
      </div>
      {actions ? <div className="flex shrink-0 items-center gap-2">{actions}</div> : null}
    </div>
  );
}
