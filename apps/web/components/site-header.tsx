"use client";

import { Button, cn } from "@via/ui";
import { Activity } from "lucide-react";
import Link from "next/link";
import { useEffect, useState } from "react";

import { ThemeToggle } from "@/components/theme-toggle";
import { ViaLogo } from "@/components/via-logo";

/** Public header: sticky, blurred, gains a hairline once the page scrolls. */
export function SiteHeader() {
  const [scrolled, setScrolled] = useState(false);
  useEffect(() => {
    const on = () => setScrolled(window.scrollY > 8);
    on();
    window.addEventListener("scroll", on, { passive: true });
    return () => window.removeEventListener("scroll", on);
  }, []);

  return (
    <header
      className={cn(
        "sticky top-0 z-40 border-b backdrop-blur-xl transition-[background-color,border-color] duration-200",
        scrolled ? "border-border bg-background/75" : "border-transparent bg-background/30",
      )}
    >
      <div className="mx-auto flex h-14 max-w-6xl items-center gap-2 px-4 sm:gap-6 sm:px-6">
        <Link href="/" aria-label="VIA home" className="rounded-sm">
          <ViaLogo />
        </Link>
        <nav aria-label="Main" className="flex items-center text-sm">
          <Link
            href="/status"
            className="inline-flex items-center gap-1.5 rounded-md px-2 py-1 text-muted transition-colors hover:bg-surface-hover hover:text-foreground"
          >
            <Activity className="size-3.5" aria-hidden="true" />
            <span className="hidden sm:inline">System status</span>
            <span className="sm:hidden">Status</span>
          </Link>
        </nav>
        <div className="ml-auto flex items-center gap-1 sm:gap-2">
          <ThemeToggle />
          <Button asChild variant="ghost" size="sm">
            <Link href="/login">Sign in</Link>
          </Button>
          <Button asChild variant="primary" size="sm" className="hidden sm:inline-flex">
            <Link href="/register">Create account</Link>
          </Button>
        </div>
      </div>
    </header>
  );
}
