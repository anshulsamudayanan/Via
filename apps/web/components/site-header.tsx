"use client";

/*
 * Floating glass navbar. Pattern from the 21st.dev "Glassmorphism Navigation" candidate
 * (@akashsingh890901-crypto): a centred translucent pill over the page. On scroll it grows more
 * opaque and slightly more compact (Motion useScroll + useTransform; the header is fixed, so its
 * size change never shifts the page).
 */

import { Button } from "@via/ui";
import { Activity } from "lucide-react";
import { m, useMotionValueEvent, useReducedMotion, useScroll, useTransform } from "motion/react";
import Link from "next/link";
import { useState } from "react";

import { ThemeToggle } from "@/components/theme-toggle";
import { ViaLogo } from "@/components/via-logo";

export function SiteHeader() {
  const reduce = useReducedMotion();
  const { scrollY } = useScroll();
  const solid = useTransform(scrollY, [0, 120], [0, 1]);
  const y = useTransform(scrollY, [0, 120], [0, reduce ? 0 : -4]);
  const [compact, setCompact] = useState(false);
  useMotionValueEvent(scrollY, "change", (v) => setCompact(v > 40));

  return (
    <>
      <m.header style={{ y }} className="fixed inset-x-0 top-0 z-40 px-3 pt-3 sm:px-6 sm:pt-4">
        <m.div
          animate={{ height: compact ? 48 : 56 }}
          transition={{ type: "spring", stiffness: 380, damping: 32 }}
          className="glass-regular relative mx-auto flex max-w-6xl items-center gap-2 rounded-full pl-4 pr-2 sm:gap-5 sm:pl-5"
        >
          {/* A denser layer fades in on scroll so text over busy content keeps its contrast. */}
          <m.span aria-hidden="true" style={{ opacity: solid }} className="pointer-events-none absolute inset-0 -z-10 rounded-full bg-[var(--via-scrim)]" />
          <Link href="/" aria-label="VIA home" className="rounded-full">
            <ViaLogo />
          </Link>
          <nav aria-label="Main" className="flex items-center text-sm">
            <Link
              href="/status"
              className="inline-flex items-center gap-1.5 rounded-full px-2.5 py-1.5 text-muted transition-colors hover:bg-surface-hover hover:text-foreground"
            >
              <Activity className="size-3.5" aria-hidden="true" />
              <span className="hidden sm:inline">System status</span>
              <span className="sm:hidden">Status</span>
            </Link>
          </nav>
          <div className="ml-auto flex items-center gap-1 sm:gap-1.5">
            <ThemeToggle />
            <Button asChild variant="ghost" size="sm">
              <Link href="/login">Sign in</Link>
            </Button>
            <Button asChild variant="primary" size="sm" className="hidden sm:inline-flex">
              <Link href="/register">Create account</Link>
            </Button>
          </div>
        </m.div>
      </m.header>
      {/* Space for the fixed header. */}
      <div aria-hidden="true" className="h-[76px] sm:h-[84px]" />
    </>
  );
}
