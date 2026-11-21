import Link from "next/link";

import { ThemeToggle } from "@/components/theme-toggle";
import { ViaLogo } from "@/components/via-logo";

const nav = [{ href: "/status", label: "System status" }];

export function SiteHeader() {
  return (
    <header className="sticky top-0 z-10 border-b border-border bg-background/90 backdrop-blur">
      <div className="mx-auto flex h-12 max-w-6xl items-center gap-6 px-4">
        <Link href="/" aria-label="VIA home" className="rounded-sm">
          <ViaLogo />
        </Link>
        <nav aria-label="Main" className="flex items-center gap-1 text-sm">
          {nav.map((item) => (
            <Link
              key={item.href}
              href={item.href}
              className="rounded-md px-2 py-1 text-muted transition-colors hover:bg-surface-hover hover:text-foreground"
            >
              {item.label}
            </Link>
          ))}
        </nav>
        <div className="ml-auto">
          <ThemeToggle />
        </div>
      </div>
    </header>
  );
}
