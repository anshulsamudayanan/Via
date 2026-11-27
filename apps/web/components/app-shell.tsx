"use client";

import { cn, Sheet, SheetContent, SheetTrigger, SPRING_SOFT } from "@via/ui";
import { m } from "motion/react";
import { Menu, Search } from "lucide-react";
import Link from "next/link";
import { type ReactNode, useEffect, useState } from "react";

import { CommandMenuProvider, useOpenCommandMenu } from "@/components/shell/command-menu";
import { SidebarContent } from "@/components/shell/sidebar";
import { setSidebarCollapsed, useSidebarCollapsed } from "@/components/shell/use-sidebar";
import { ViaLogo } from "@/components/via-logo";

function isTyping(target: EventTarget | null): boolean {
  const el = target as HTMLElement | null;
  return Boolean(el && (el.isContentEditable || ["INPUT", "TEXTAREA", "SELECT"].includes(el.tagName)));
}

function MobileTopBar() {
  const [open, setOpen] = useState(false);
  const openSearch = useOpenCommandMenu();
  return (
    <header className="glass-thick sticky top-2 z-30 mx-2 mt-2 flex h-12 items-center gap-1 rounded-full px-1.5 md:hidden">
      <Sheet open={open} onOpenChange={setOpen}>
        <SheetTrigger
          aria-label="Open navigation"
          className="flex size-9 items-center justify-center rounded-full text-muted hover:bg-surface-hover hover:text-foreground [&>svg]:size-5"
        >
          <Menu aria-hidden="true" />
        </SheetTrigger>
        <SheetContent title="Navigation">
          <SidebarContent layoutGroup="mobile" onNavigate={() => setOpen(false)} />
        </SheetContent>
      </Sheet>
      <Link href="/dashboard" aria-label="VIA dashboard" className="rounded-sm px-1">
        <ViaLogo />
      </Link>
      <button
        type="button"
        onClick={openSearch}
        aria-label="Search"
        className="ml-auto flex size-9 items-center justify-center rounded-full text-muted hover:bg-surface-hover hover:text-foreground [&>svg]:size-5"
      >
        <Search aria-hidden="true" />
      </button>
    </header>
  );
}

export function AppShell({ children }: { children: ReactNode }) {
  const collapsed = useSidebarCollapsed();
  useEffect(() => {
    function onKey(e: KeyboardEvent) {
      if (e.key === "[" && !e.metaKey && !e.ctrlKey && !e.altKey && !isTyping(e.target)) setSidebarCollapsed(!collapsed);
    }
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [collapsed]);

  return (
        <CommandMenuProvider>
          <div className="flex min-h-dvh flex-col md:flex-row">
            <MobileTopBar />
            {/* Floating glass sidebar; collapsing is a Motion layout animation. */}
            <m.aside
              layout
              transition={SPRING_SOFT}
              aria-label="Sidebar"
              className={cn("hidden shrink-0 p-3 pr-0 md:sticky md:top-0 md:block md:h-dvh", collapsed ? "w-[76px]" : "w-[260px]")}
            >
              <m.div layout transition={SPRING_SOFT} className="glass-thick h-full overflow-hidden rounded-3xl">
                <SidebarContent layoutGroup="desktop" collapsed={collapsed} onToggleCollapsed={() => setSidebarCollapsed(!collapsed)} />
              </m.div>
            </m.aside>
            <main id="main" className="min-w-0 flex-1">
              <div className="mx-auto max-w-[1440px] px-4 py-5 md:px-7 md:py-6">{children}</div>
            </main>
          </div>
        </CommandMenuProvider>
  );
}

/** Consistent page heading with optional actions on the right. */
export function PageHeader({ title, description, actions }: { title: ReactNode; description?: ReactNode; actions?: ReactNode }) {
  return (
    <div className="mb-6 flex flex-wrap items-center justify-between gap-x-4 gap-y-3">
      <div className="min-w-0">
        <h1 className="truncate font-display text-[28px] font-normal leading-9 tracking-[-0.02em]">{title}</h1>
        {description ? <div className="mt-0.5 text-[14px] text-muted">{description}</div> : null}
      </div>
      {actions ? <div className="flex flex-wrap items-center gap-2">{actions}</div> : null}
    </div>
  );
}
