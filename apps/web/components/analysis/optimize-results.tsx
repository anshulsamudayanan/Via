"use client";

import type { AreaAnalysis, BomAnalysis, Candidate, MarginAnalysis, OptimizationRun, SourcingStrategy } from "@via/types";
import { Badge, Button, Card, CardHeader, CardTitle, ErrorState, Skeleton, Table, TBody, TD, TH, THead, TR } from "@via/ui";
import { useState } from "react";

import { useApi } from "@/components/api-context";
import { errorMessage } from "@/lib/errors";
import { formatMetric, metricLabel } from "@/lib/findings";
import { useAsync } from "@/lib/use-async";

const pct = (v: number | null | undefined) => (v === null || v === undefined ? "n/a" : `${(v * 100).toFixed(1)}%`);

function AreaSection({ area }: { area: AreaAnalysis }) {
  if (!area.available) return <p className="text-xs text-muted">{area.observations.join(" ")}</p>;
  const margin = area.unused_margin_mm;
  const empty = area.largest_empty_rectangle;
  return (
    <div className="space-y-2">
      <dl className="grid gap-x-6 gap-y-1 text-xs sm:grid-cols-2">
        <div className="flex justify-between gap-2"><dt className="text-muted">Board</dt><dd className="font-mono">{area.board_width_mm} × {area.board_height_mm} mm ({area.outline_area_mm2} mm²)</dd></div>
        <div className="flex justify-between gap-2"><dt className="text-muted">Covered by parts</dt><dd className="font-mono">{pct(area.utilisation)} ({area.occupied_area_mm2} mm²)</dd></div>
        {margin ? <div className="flex justify-between gap-2"><dt className="text-muted">Unused margin (L / T / R / B)</dt><dd className="font-mono">{margin.left} / {margin.top} / {margin.right} / {margin.bottom} mm</dd></div> : null}
        <div className="flex justify-between gap-2"><dt className="text-muted">Largest empty rectangle</dt><dd className="font-mono">{empty ? `${empty.width_mm} × ${empty.height_mm} mm` : "not computed"}</dd></div>
      </dl>
      {area.density_grid ? (
        <div role="img" aria-label="Where the parts sit on the board: darker blocks are more densely covered" className="grid w-40 grid-cols-6 gap-px rounded border border-border p-px">
          {area.density_grid.flat().map((v, i) => <span key={i} className="aspect-square bg-foreground" style={{ opacity: 0.06 + Math.min(v, 1) * 0.7 }} />)}
        </div>
      ) : null}
      {area.observations.length ? <ul className="list-disc pl-4 text-xs text-muted">{area.observations.map((o, i) => <li key={i}>{o}</li>)}</ul> : null}
      <p className="text-xs text-subtle">Measured on a {area.resolution_mm} mm grid from part extents (courtyards when present). Empty space ignores copper pours.</p>
    </div>
  );
}

function MarginsSection({ margins }: { margins: MarginAnalysis }) {
  const ran = margins.rules.filter((r) => r.ran);
  const skipped = margins.rules.filter((r) => !r.ran);
  return (
    <div className="space-y-2">
      <p className="text-xs text-muted">
        Profile: {margins.profile.name}. {margins.violating_features} feature{margins.violating_features === 1 ? "" : "s"} break it; {margins.potential_risk_features} more are within {Math.round(margins.risk_fraction * 100)}% above a limit.
      </p>
      <Table>
        <THead><TR><TH>Rule</TH><TH>Limit</TH><TH>Breaking it</TH><TH>Close to the limit</TH></TR></THead>
        <TBody>
          {ran.map((r) => (
            <TR key={r.check}>
              <TD>{r.title}</TD>
              <TD className="font-mono text-xs">{Object.values(r.limits ?? {}).join(" / ")}</TD>
              <TD className="font-mono">{r.violating_features ?? 0}</TD>
              <TD className="font-mono">{r.potential_risk_features ?? 0}</TD>
            </TR>
          ))}
        </TBody>
      </Table>
      {skipped.length ? <p className="text-xs text-muted">Not run: {skipped.map((r) => `${r.title} (${r.reason})`).join("; ")}</p> : null}
      <ul className="list-disc pl-4 text-xs text-subtle">{margins.notes.map((n, i) => <li key={i}>{n}</li>)}</ul>
    </div>
  );
}

const STRATEGY: Record<SourcingStrategy, { label: string; hint: string }> = {
  cheapest: { label: "Cheapest", hint: "Lowest total for the quantity, buying up to a better price break when that costs less" },
  fastest: { label: "Fastest", hint: "What the supplier can ship from stock now; otherwise the shortest stated lead time" },
  balanced: { label: "Balanced", hint: "Equal weight on cost and lead time (a lead time of 28 days or more counts as worst)" },
};

function BomSection({ bom }: { bom: BomAnalysis }) {
  const [strategy, setStrategy] = useState<SourcingStrategy>("cheapest");
  if (!bom.strategies || !Object.keys(bom.strategies).length) {
    return (
      <div className="space-y-2">
        <p className="text-xs text-muted">Not priced: {bom.reason ?? "no listing matched the part numbers."}</p>
        {unpriced(bom)}
      </div>
    );
  }
  const plan = bom.strategies[strategy] ?? { total: 0, lines: [] };
  const money = (v: number) => new Intl.NumberFormat(undefined, { style: "currency", currency: bom.currency ?? "USD", maximumFractionDigits: 4 }).format(v);
  return (
    <div className="space-y-2">
      <p className="text-xs text-muted">
        {bom.supplier} listings for {bom.build_quantity} board{bom.build_quantity === 1 ? "" : "s"}: {bom.lines_priced} of {bom.lines} BOM lines priced.
        {bom.lines_priced !== bom.lines ? " The totals cover only the priced lines." : ""}
      </p>
      <div role="group" aria-label="Sourcing strategy" className="flex flex-wrap gap-1.5">
        {(Object.keys(STRATEGY) as SourcingStrategy[]).filter((k) => bom.strategies?.[k]).map((k) => (
          <Button key={k} size="sm" variant={k === strategy ? "outline" : "ghost"} aria-pressed={k === strategy} title={STRATEGY[k].hint} onClick={() => setStrategy(k)}>
            {STRATEGY[k].label} · {money(bom.strategies?.[k]?.total ?? 0)}
          </Button>
        ))}
      </div>
      <p className="text-xs text-subtle">{STRATEGY[strategy].hint}.</p>
      <Table>
        <THead><TR><TH>Part</TH><TH>Need</TH><TH>Order</TH><TH>Unit</TH><TH>Total</TH><TH>Stock</TH></TR></THead>
        <TBody>
          {plan.lines.map((l) => (
            <TR key={l.key}>
              <TD><span className="font-mono">{l.mpn}</span> <span className="text-xs text-muted">{l.references.slice(0, 4).join(", ")}{l.references.length > 4 ? "…" : ""}</span></TD>
              <TD className="font-mono">{l.needed}</TD>
              <TD className="font-mono">{l.order_qty}{l.overbuy > 0 ? <span className="text-xs text-muted"> (+{l.overbuy})</span> : null}</TD>
              <TD className="font-mono">{money(l.unit_price)}</TD>
              <TD className="font-mono">{money(l.total)}</TD>
              <TD className="text-xs">{l.in_stock === true ? "in stock" : l.in_stock === false ? `not in stock${l.lead_time_days !== null ? ` · ${l.lead_time_days} days` : ""}` : "stock unknown"}</TD>
            </TR>
          ))}
        </TBody>
      </Table>
      {unpriced(bom)}
      <ul className="list-disc pl-4 text-xs text-subtle">{(bom.notes ?? []).map((n, i) => <li key={i}>{n}</li>)}</ul>
    </div>
  );
}

function unpriced(bom: BomAnalysis) {
  const rows = bom.unpriced ?? [];
  if (!rows.length) return null;
  return (
    <details className="text-xs">
      <summary className="cursor-pointer text-accent">Not priced ({rows.length})</summary>
      <ul className="mt-1 space-y-0.5 text-muted">{rows.map((u) => <li key={u.key}><span className="font-mono">{u.references.slice(0, 3).join(", ")}</span>: {u.reason}</li>)}</ul>
    </details>
  );
}

export function AnalysisCards({ run }: { run: OptimizationRun }) {
  const a = run.summary.analysis;
  if (!a || (!a.area && !a.margins && !a.bom)) return null;
  return (
    <>
      {a.area ? <Card><CardHeader><CardTitle>Board area</CardTitle></CardHeader><div className="px-4 pb-4"><AreaSection area={a.area} /></div></Card> : null}
      {a.margins ? <Card><CardHeader><CardTitle>Manufacturing margins</CardTitle></CardHeader><div className="px-4 pb-4"><MarginsSection margins={a.margins} /></div></Card> : null}
      {a.bom ? <Card><CardHeader><CardTitle>Supplier pricing</CardTitle></CardHeader><div className="px-4 pb-4"><BomSection bom={a.bom} /></div></Card> : null}
    </>
  );
}

/** Original design beside every candidate, only for metrics that were calculated. */
export function ComparisonTable({ run, candidates }: { run: OptimizationRun; candidates: Candidate[] }) {
  const client = useApi();
  const cmp = useAsync((s) => client.optimization.compare(run.id, s), [client, run.id]);
  if (cmp.error) return <ErrorState title="Couldn't load the comparison" description={errorMessage(cmp.error)} />;
  if (!cmp.data) return <Skeleton className="h-24 w-full" />;
  const { baseline, rows } = cmp.data;
  const metrics = cmp.data.metrics.filter((m) => baseline[m] !== null && baseline[m] !== undefined && rows.some((r) => r.metrics[m] !== null && r.metrics[m] !== undefined));
  if (!rows.length || !metrics.length) return null;
  const byId = new Map(candidates.map((c) => [c.id, c]));
  return (
    <div className="overflow-x-auto px-4 pb-3">
      <Table>
        <THead>
          <TR>
            <TH>Metric (lower is better)</TH>
            <TH>Original</TH>
            {rows.map((r) => <TH key={r.id}>{r.title}</TH>)}
          </TR>
        </THead>
        <TBody>
          {metrics.map((m) => (
            <TR key={m}>
              <TD>{metricLabel(m)}</TD>
              <TD className="font-mono">{formatMetric(m, baseline[m])}</TD>
              {rows.map((r) => {
                const d = r.deltas[m];
                const value = r.metrics[m];
                return (
                  <TD key={r.id} className="font-mono">
                    {value === null || value === undefined ? "n/a" : formatMetric(m, value)}
                    {d ? <span className={d < 0 ? "ml-1 text-xs text-success" : "ml-1 text-xs text-danger"}>{d > 0 ? "+" : ""}{Number(d.toFixed(3))}</span> : null}
                  </TD>
                );
              })}
            </TR>
          ))}
          <TR>
            <TD>Status</TD>
            <TD className="text-xs text-muted">original</TD>
            {rows.map((r) => <TD key={r.id}><Badge>{byId.get(r.id)?.lifecycle.replace("_", " ") ?? r.status}</Badge></TD>)}
          </TR>
        </TBody>
      </Table>
      <p className="mt-1 text-xs text-subtle">Only metrics VIA calculated are shown; n/a means the candidate has no value to compare (for example a manual change).</p>
    </div>
  );
}
