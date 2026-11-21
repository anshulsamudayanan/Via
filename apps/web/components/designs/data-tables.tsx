"use client";

import type { PcbComponent } from "@via/types";
import { Badge, Button, Card, EmptyState, ErrorState, Input, Select, Skeleton, Table, TBody, TD, TH, THead, TR } from "@via/ui";
import { ChevronLeft, ChevronRight, Search } from "lucide-react";
import { type ReactNode, useEffect, useState } from "react";

import { useApi } from "@/components/api-context";
import { errorMessage } from "@/lib/errors";
import { mm } from "@/lib/format";
import { useAsync } from "@/lib/use-async";

const PAGE = 50;

function useDebounced(value: string, ms = 250): string {
  const [debounced, setDebounced] = useState(value);
  useEffect(() => {
    const id = window.setTimeout(() => setDebounced(value), ms);
    return () => window.clearTimeout(id);
  }, [value, ms]);
  return debounced;
}

function Pager({ offset, count, total, onChange }: { offset: number; count: number; total: number; onChange: (o: number) => void }) {
  return (
    <div className="flex items-center justify-between border-t border-border px-3 py-2 text-xs text-muted">
      <span>{total ? `${offset + 1}–${offset + count} of ${total}` : "0 results"}</span>
      <div className="flex gap-1">
        <Button size="sm" variant="ghost" aria-label="Previous page" disabled={offset === 0} onClick={() => onChange(Math.max(0, offset - PAGE))}>
          <ChevronLeft />
        </Button>
        <Button size="sm" variant="ghost" aria-label="Next page" disabled={offset + PAGE >= total} onClick={() => onChange(offset + PAGE)}>
          <ChevronRight />
        </Button>
      </div>
    </div>
  );
}

function SearchBox({ label, value, onChange, children }: { label: string; value: string; onChange: (v: string) => void; children?: ReactNode }) {
  return (
    <div className="flex flex-wrap items-center gap-2 border-b border-border p-2">
      <div className="relative min-w-48 flex-1">
        <Search className="pointer-events-none absolute top-1/2 left-2.5 size-3.5 -translate-y-1/2 text-subtle" aria-hidden="true" />
        <Input type="search" aria-label={label} placeholder={label} className="pl-8" maxLength={100} value={value} onChange={(e) => onChange(e.target.value)} />
      </div>
      {children}
    </div>
  );
}

export function ComponentsTable({ designId, revisionId, onSelect }: { designId: string; revisionId?: string; onSelect?: (c: PcbComponent) => void }) {
  const client = useApi();
  const [q, setQ] = useState("");
  const [side, setSide] = useState<"" | "top" | "bottom">("");
  const [offset, setOffset] = useState(0);
  const query = useDebounced(q);
  const result = useAsync(
    (signal) => client.pcb.components(designId, { q: query || undefined, side: side || undefined, revision_id: revisionId, limit: PAGE, offset }, signal),
    [client, designId, revisionId, query, side, offset],
  );
  return (
    <Card>
      <SearchBox
        label="Search reference, value or footprint"
        value={q}
        onChange={(v) => {
          setQ(v);
          setOffset(0);
        }}
      >
        <Select aria-label="Board side" className="w-auto" value={side} onChange={(e) => { setSide(e.target.value as typeof side); setOffset(0); }}>
          <option value="">Both sides</option>
          <option value="top">Top</option>
          <option value="bottom">Bottom</option>
        </Select>
      </SearchBox>
      {result.error ? (
        <ErrorState className="m-3" title="Couldn't load components" description={errorMessage(result.error)} />
      ) : !result.data ? (
        <div className="space-y-2 p-3">{Array.from({ length: 5 }, (_, i) => <Skeleton key={i} className="h-7 w-full" />)}</div>
      ) : result.data.items.length === 0 ? (
        <EmptyState title={query || side ? "No matching components" : "No components on this board"} />
      ) : (
        <>
          <Table>
            <caption className="sr-only">Components</caption>
            <THead>
              <tr>
                <TH>Ref</TH>
                <TH>Value</TH>
                <TH className="hidden md:table-cell">Footprint</TH>
                <TH>Side</TH>
                <TH className="hidden text-right sm:table-cell">X</TH>
                <TH className="hidden text-right sm:table-cell">Y</TH>
                <TH className="hidden text-right sm:table-cell">Rot</TH>
                <TH className="hidden text-right lg:table-cell">Pads</TH>
              </tr>
            </THead>
            <TBody>
              {result.data.items.map((c) => (
                <TR key={c.id} className={onSelect ? "cursor-pointer hover:bg-surface-hover" : undefined} onClick={onSelect ? () => onSelect(c) : undefined}>
                  <TD className="font-mono text-xs font-medium">{c.reference || <span className="text-subtle">(none)</span>}</TD>
                  <TD className="max-w-40 truncate">{c.value ?? "-"}</TD>
                  <TD className="hidden max-w-64 truncate font-mono text-xs text-muted md:table-cell" title={c.footprint}>{c.footprint}</TD>
                  <TD><Badge tone={c.side === "bottom" ? "warning" : "neutral"}>{c.side}</Badge></TD>
                  <TD className="hidden text-right font-mono text-xs tabular-nums sm:table-cell">{c.x.toFixed(3)}</TD>
                  <TD className="hidden text-right font-mono text-xs tabular-nums sm:table-cell">{c.y.toFixed(3)}</TD>
                  <TD className="hidden text-right font-mono text-xs tabular-nums sm:table-cell">{c.rotation}°</TD>
                  <TD className="hidden text-right font-mono text-xs tabular-nums lg:table-cell">{c.pad_count}</TD>
                </TR>
              ))}
            </TBody>
          </Table>
          <Pager offset={offset} count={result.data.items.length} total={result.data.total} onChange={setOffset} />
        </>
      )}
    </Card>
  );
}

export function NetsTable({ designId, revisionId }: { designId: string; revisionId?: string }) {
  const client = useApi();
  const [q, setQ] = useState("");
  const [offset, setOffset] = useState(0);
  const query = useDebounced(q);
  const result = useAsync(
    (signal) => client.pcb.nets(designId, { q: query || undefined, revision_id: revisionId, limit: PAGE, offset }, signal),
    [client, designId, revisionId, query, offset],
  );
  return (
    <Card>
      <SearchBox label="Search nets" value={q} onChange={(v) => { setQ(v); setOffset(0); }} />
      {result.error ? (
        <ErrorState className="m-3" title="Couldn't load nets" description={errorMessage(result.error)} />
      ) : !result.data ? (
        <div className="space-y-2 p-3">{Array.from({ length: 5 }, (_, i) => <Skeleton key={i} className="h-7 w-full" />)}</div>
      ) : result.data.items.length === 0 ? (
        <EmptyState title={query ? "No matching nets" : "No nets on this board"} />
      ) : (
        <>
          <Table>
            <caption className="sr-only">Nets</caption>
            <THead>
              <tr>
                <TH>Net</TH>
                <TH className="text-right">Pads</TH>
                <TH className="text-right">Tracks</TH>
                <TH className="text-right">Vias</TH>
                <TH className="text-right">Track length</TH>
              </tr>
            </THead>
            <TBody>
              {result.data.items.map((n) => (
                <TR key={n.id}>
                  <TD className="max-w-72 truncate font-mono text-xs" title={n.name}>{n.name}</TD>
                  <TD className="text-right font-mono text-xs tabular-nums">{n.pad_count}</TD>
                  <TD className="text-right font-mono text-xs tabular-nums">{n.track_count}</TD>
                  <TD className="text-right font-mono text-xs tabular-nums">{n.via_count}</TD>
                  <TD className="text-right font-mono text-xs tabular-nums">{mm(n.track_length)}</TD>
                </TR>
              ))}
            </TBody>
          </Table>
          <Pager offset={offset} count={result.data.items.length} total={result.data.total} onChange={setOffset} />
        </>
      )}
    </Card>
  );
}

const KIND_LABEL: Record<string, string> = {
  copper: "Copper", silkscreen: "Silkscreen", solder_mask: "Solder mask", solder_paste: "Solder paste",
  adhesive: "Adhesive", fabrication: "Fabrication", courtyard: "Courtyard", edge: "Board edge",
  margin: "Margin", documentation: "Documentation", user: "User",
};

export function LayersTable({ designId, revisionId }: { designId: string; revisionId?: string }) {
  const client = useApi();
  const result = useAsync(() => client.pcb.layers(designId, revisionId), [client, designId, revisionId]);
  if (result.error) return <ErrorState title="Couldn't load layers" description={errorMessage(result.error)} />;
  if (!result.data) return <Skeleton className="h-40 w-full" />;
  return (
    <Card>
      <Table>
        <caption className="sr-only">Layers</caption>
        <THead>
          <tr>
            <TH className="w-16 text-right">#</TH>
            <TH>Name</TH>
            <TH>Kind</TH>
            <TH>Side</TH>
            <TH className="hidden sm:table-cell">Type in file</TH>
            <TH className="hidden md:table-cell">User name</TH>
          </tr>
        </THead>
        <TBody>
          {result.data.map((l) => (
            <TR key={l.name}>
              <TD className="text-right font-mono text-xs text-muted tabular-nums">{l.ordinal}</TD>
              <TD className="font-mono text-xs">{l.name}</TD>
              <TD>{l.kind === "copper" ? <Badge tone="accent">Copper</Badge> : <span className="text-muted">{KIND_LABEL[l.kind] ?? l.kind}</span>}</TD>
              <TD className="text-muted">{l.side === "none" ? "-" : l.side}</TD>
              <TD className="hidden font-mono text-xs text-muted sm:table-cell">{l.source_type ?? "-"}</TD>
              <TD className="hidden text-muted md:table-cell">{l.user_name ?? "-"}</TD>
            </TR>
          ))}
        </TBody>
      </Table>
    </Card>
  );
}
