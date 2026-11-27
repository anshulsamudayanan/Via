"use client";

/*
 * Floating glass navbar. Pattern from the 21st.dev "Glassmorphism Navigation" candidate
 * (@akashsingh890901-crypto): a centred translucent bar over the page. On scroll a denser layer fades
 * in behind it (opacity only) so its text keeps contrast over busy content.
 */

import { Button, Kbd } from "@via/ui";
import { Activity, Search } from "lucide-react";
import { m, useScroll, useTransform } from "motion/react";
import Link from "next/link";
import { useRouter } from "next/navigation";
import { useEffect } from "react";

import { ThemeToggle } from "@/components/theme-toggle";
import { ViaLogo } from "@/components/via-logo";

export function SiteHeader() {
  const { scrollY } = useScroll();
  const solid = useTransform(scrollY, [0, 120], [0, 1]);
  const router = useRouter();
  // "/" opens project search, which lives in the app (signed-out visitors land on sign-in first).
  useEffect(() => {
    function onKey(e: KeyboardEvent) {
      const el = e.target as HTMLElement | null;
      if (e.key !== "/" || e.metaKey || e.ctrlKey || e.altKey) return;
      if (el && (el.isContentEditable || ["INPUT", "TEXTAREA", "SELECT"].includes(el.tagName))) return;
      e.preventDefault();
      router.push("/dashboard");
    }
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [router]);

  return (
    <>
      <header className="fixed inset-x-0 top-0 z-40 px-3 pt-3 sm:px-6 sm:pt-4">
        <div className="glass-thick relative mx-auto flex h-14 max-w-6xl items-center gap-2 rounded-2xl pl-4 pr-2 sm:gap-5 sm:pl-5">
          {/* A denser layer fades in on scroll so text over busy content keeps its contrast. */}
          <m.span aria-hidden="true" style={{ opacity: solid }} className="pointer-events-none absolute inset-0 -z-10 rounded-[inherit] bg-[var(--via-scrim)]" />
          <Link href="/" aria-label="VIA home" className="rounded-full">
            <ViaLogo />
          </Link>
          <nav aria-label="Main" className="flex items-center gap-1 text-sm">
            <Link
              href="/status"
              className="inline-flex items-center gap-1.5 rounded-lg px-2.5 py-1.5 text-muted transition-colors hover:bg-surface-hover hover:text-foreground"
            >
              <Activity className="size-3.5" aria-hidden="true" />
              <span className="hidden sm:inline">System status</span>
              <span className="sm:hidden">Status</span>
            </Link>
          </nav>
          <Link
            href="/dashboard"
            aria-keyshortcuts="/"
            className="mx-auto hidden h-9 w-full max-w-sm items-center gap-2.5 rounded-lg border border-border bg-surface-sunken px-3.5 text-[13px] text-subtle shadow-[inset_0_1px_0_var(--via-glass-highlight)] transition-colors hover:border-border-strong hover:text-muted md:flex"
          >
            <Search className="size-4" aria-hidden="true" />
            <span className="flex-1">Search your projects</span>
            <Kbd>/</Kbd>
          </Link>
          <div className="ml-auto flex items-center gap-1 sm:gap-1.5 md:ml-0">
            <ThemeToggle />
            <Button asChild variant="ghost" size="md" className="text-foreground">
              <Link href="/login">Sign in</Link>
            </Button>
            <Button asChild variant="primary" size="md" className="hidden sm:inline-flex">
              <Link href="/register">Create account</Link>
            </Button>
          </div>
        </div>
      </header>
      {/* Space for the fixed header. */}
      <div aria-hidden="true" className="h-[76px] sm:h-[84px]" />
    </>
  );
}
