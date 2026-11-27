"use client";

import type { ReadinessResponse } from "@via/types";
import { cn, StatusDot, type StatusTone, Tooltip } from "@via/ui";
import Link from "next/link";
import { useEffect, useState } from "react";

import { useApi } from "@/components/api-context";

type Health = { tone: StatusTone; label: string };

const CHECKING: Health = { tone: "unknown", label: "Checking status…" };

function summarize(data: ReadinessResponse): Health {
  return data.status === "ok" ? { tone: "ok", label: "All systems operational" } : { tone: "warning", label: "Degraded service" };
}

/**
 * The real readiness probe (GET /health/ready), polled once a minute, linking to the full status page.
 * Collapsed sidebars show only the dot, with the label in a tooltip.
 */
export function StatusIndicator({ collapsed = false, onNavigate }: { collapsed?: boolean; onNavigate?: () => void }) {
  const client = useApi();
  const [health, setHealth] = useState<Health>(CHECKING);

  useEffect(() => {
    let ac = new AbortController();
    const load = () => {
      ac.abort();
      ac = new AbortController();
      client.health.ready(ac.signal).then(
        (d) => setHealth(summarize(d)),
        (err: unknown) => {
          if (!(err instanceof DOMException && err.name === "AbortError")) setHealth({ tone: "error", label: "API unreachable" });
        },
      );
    };
    load();
    const id = window.setInterval(load, 60_000);
    return () => {
      window.clearInterval(id);
      ac.abort();
    };
  }, [client]);

  const link = (
    <Link
      href="/status"
      onClick={onNavigate}
      aria-label={collapsed ? `System status: ${health.label}` : undefined}
      className={cn(
        "flex h-7 items-center gap-2 rounded-md text-xs text-muted hover:bg-surface-hover hover:text-foreground",
        collapsed ? "w-8 justify-center" : "px-2",
      )}
    >
      <StatusDot tone={health.tone} />
      {collapsed ? null : (
        <span className="truncate" aria-live="polite">
          {health.label}
        </span>
      )}
    </Link>
  );
  return collapsed ? (
    <Tooltip content={`System status: ${health.label}`} side="right">
      {link}
    </Tooltip>
  ) : (
    link
  );
}
