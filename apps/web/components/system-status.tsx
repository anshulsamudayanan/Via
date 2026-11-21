"use client";

import type { ApiError, ViaClient } from "@via/api-client";
import type { ReadinessResponse } from "@via/types";
import { Badge, Button, Card, CardContent, CardDescription, CardHeader, CardTitle, ErrorState, Skeleton, StatusDot } from "@via/ui";
import { AlertTriangle, RefreshCw } from "lucide-react";
import { useCallback, useEffect, useRef, useState } from "react";

import { api as defaultClient } from "@/lib/api";

const CHECK_LABELS: Record<string, { label: string; description: string }> = {
  database: { label: "Database", description: "PostgreSQL connectivity and migration state" },
  redis: { label: "Redis", description: "Queue and rate-limit store" },
  storage: { label: "Object storage", description: "Design file storage (S3-compatible)" },
};

type State =
  | { kind: "loading" }
  | { kind: "loaded"; data: ReadinessResponse; checkedAt: Date }
  | { kind: "unreachable"; error: ApiError; checkedAt: Date };

interface Props {
  client?: Pick<ViaClient, "health">;
  /** Polling interval in ms; 0 disables polling. */
  pollMs?: number;
  /** Compact summary (one line) instead of the full table. */
  compact?: boolean;
}

export function SystemStatus({ client = defaultClient, pollMs = 15000, compact = false }: Props) {
  const [state, setState] = useState<State>({ kind: "loading" });
  const [refreshing, setRefreshing] = useState(false);
  const controller = useRef<AbortController | null>(null);

  const load = useCallback(async () => {
    controller.current?.abort();
    const ac = new AbortController();
    controller.current = ac;
    setRefreshing(true);
    try {
      const data = await client.health.ready(ac.signal);
      setState({ kind: "loaded", data, checkedAt: new Date() });
    } catch (err) {
      if (err instanceof DOMException && err.name === "AbortError") return;
      setState({ kind: "unreachable", error: err as ApiError, checkedAt: new Date() });
    } finally {
      if (!ac.signal.aborted) setRefreshing(false);
    }
  }, [client]);

  useEffect(() => {
    // Initial fetch, then poll. Data fetching from an effect is the intended use here.
    // eslint-disable-next-line react-hooks/set-state-in-effect
    void load();
    if (!pollMs) return () => controller.current?.abort();
    const id = window.setInterval(() => void load(), pollMs);
    return () => {
      window.clearInterval(id);
      controller.current?.abort();
    };
  }, [load, pollMs]);

  const summary = summarize(state);

  if (compact) {
    return (
      <div className="flex items-center gap-2 text-sm" aria-live="polite">
        {state.kind === "loading" ? (
          <Skeleton className="h-4 w-40" />
        ) : (
          <>
            <StatusDot tone={summary.tone} />
            <span className="text-foreground">{summary.title}</span>
          </>
        )}
      </div>
    );
  }

  return (
    <Card>
      <CardHeader>
        <div>
          <CardTitle>Service health</CardTitle>
          <CardDescription>Live readiness of the VIA API and its dependencies.</CardDescription>
        </div>
        <Button size="sm" variant="secondary" onClick={() => void load()} disabled={refreshing} aria-label="Refresh status">
          <RefreshCw className={refreshing ? "animate-spin" : undefined} />
          Refresh
        </Button>
      </CardHeader>
      <CardContent className="space-y-3">
        <div className="flex flex-wrap items-center gap-3" aria-live="polite">
          {state.kind === "loading" ? (
            <Skeleton className="h-5 w-48" />
          ) : (
            <>
              <Badge tone={summary.tone === "ok" ? "success" : "danger"}>{summary.title}</Badge>
              {state.kind === "loaded" ? (
                <span className="font-mono text-xs text-muted">API v{state.data.version}</span>
              ) : null}
              <span className="text-xs text-subtle">Checked {state.checkedAt.toLocaleTimeString()}</span>
            </>
          )}
        </div>

        {state.kind === "unreachable" ? (
          <ErrorState
            icon={<AlertTriangle />}
            title="The VIA API is not reachable"
            description={
              <>
                {state.error.message}
                {state.error.requestId ? <span className="font-mono"> (request {state.error.requestId})</span> : null}
              </>
            }
          />
        ) : null}

        <table className="w-full text-sm">
          <caption className="sr-only">Dependency checks</caption>
          <thead>
            <tr className="border-b border-border text-left text-xs text-muted">
              <th scope="col" className="py-2 pr-3 font-medium">
                Component
              </th>
              <th scope="col" className="py-2 pr-3 font-medium">
                Status
              </th>
              <th scope="col" className="py-2 pr-3 text-right font-medium">
                Latency
              </th>
              <th scope="col" className="hidden py-2 font-medium sm:table-cell">
                Detail
              </th>
            </tr>
          </thead>
          <tbody>
            {Object.entries(CHECK_LABELS).map(([key, meta]) => {
              const check = state.kind === "loaded" ? state.data.checks[key] : undefined;
              return (
                <tr key={key} className="border-b border-border last:border-0">
                  <th scope="row" className="py-2 pr-3 text-left font-normal">
                    <div className="text-foreground">{meta.label}</div>
                    <div className="text-xs text-subtle">{meta.description}</div>
                  </th>
                  <td className="py-2 pr-3">
                    {state.kind === "loading" ? (
                      <Skeleton className="h-4 w-16" />
                    ) : (
                      <span className="inline-flex items-center gap-1.5">
                        <StatusDot tone={check ? (check.status === "ok" ? "ok" : "error") : "unknown"} />
                        {check ? (check.status === "ok" ? "Operational" : "Unavailable") : "Unknown"}
                      </span>
                    )}
                  </td>
                  <td className="py-2 pr-3 text-right font-mono text-xs text-muted tabular-nums">
                    {check ? `${check.latency_ms.toFixed(1)} ms` : "-"}
                  </td>
                  <td className="hidden py-2 font-mono text-xs text-muted sm:table-cell">{check?.detail ?? "-"}</td>
                </tr>
              );
            })}
          </tbody>
        </table>
      </CardContent>
    </Card>
  );
}

function summarize(state: State): { tone: "ok" | "error" | "unknown"; title: string } {
  if (state.kind === "loading") return { tone: "unknown", title: "Checking..." };
  if (state.kind === "unreachable") return { tone: "error", title: "API unreachable" };
  const failing = Object.entries(state.data.checks)
    .filter(([, c]) => c.status !== "ok")
    .map(([k]) => CHECK_LABELS[k]?.label ?? k);
  if (failing.length === 0) return { tone: "ok", title: "All systems operational" };
  return { tone: "error", title: `Degraded: ${failing.join(", ")} unavailable` };
}
