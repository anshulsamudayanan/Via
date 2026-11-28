"use client";

import type { Objective } from "@via/types";
import { Button, Input } from "@via/ui";
import { Plus, X } from "lucide-react";
import { useState } from "react";

import { useApi } from "@/components/api-context";
import { errorMessage } from "@/lib/errors";
import { useAsync } from "@/lib/use-async";

export interface Requirement {
  kind: string;
  description: string;
  hard: boolean;
}

export interface ConstraintsInput {
  edge_margin_mm: string;
  component_gap_mm: string;
  fixed_components: string;
  max_board_width_mm: string;
  max_board_height_mm: string;
  outline_fixed: boolean;
  keep_locked_fixed: boolean;
  keep_connectors_fixed: boolean;
  allow_rotation: boolean;
  requirements: Requirement[];
}

export const DEFAULT_CONSTRAINTS: ConstraintsInput = {
  edge_margin_mm: "1",
  component_gap_mm: "0.25",
  fixed_components: "",
  max_board_width_mm: "",
  max_board_height_mm: "",
  outline_fixed: false,
  keep_locked_fixed: true,
  keep_connectors_fixed: true,
  allow_rotation: true,
  requirements: [],
};

/** Requirement kinds VIA can record but cannot evaluate: each is reported as unverified. */
const REQUIREMENT_KINDS = ["impedance_targets", "length_matching", "differential_pair_skew", "signal_integrity", "thermal_simulation", "emc", "enclosure_fit", "creepage_and_voltage_clearance"];

type Parsed<T> = { ok: true; value: T } | { ok: false; error: string };

function num(label: string, text: string, min: number, max: number, optional = false): Parsed<number | undefined> {
  if (!text.trim()) return optional ? { ok: true, value: undefined } : { ok: false, error: `${label} is required.` };
  const n = Number(text);
  if (!Number.isFinite(n) || n < min || n > max) return { ok: false, error: `${label} must be between ${min} and ${max}.` };
  return { ok: true, value: n };
}

/** The API's constraints body from the form, or the first problem to show. */
export function constraintsBody(c: ConstraintsInput): Parsed<Record<string, unknown>> {
  const margin = num("Edge margin", c.edge_margin_mm, 0, 50);
  const gap = num("Component gap", c.component_gap_mm, 0, 20);
  const width = num("Maximum width", c.max_board_width_mm, 0.001, 100000, true);
  const height = num("Maximum height", c.max_board_height_mm, 0.001, 100000, true);
  for (const r of [margin, gap, width, height]) if (!r.ok) return r;
  const body: Record<string, unknown> = {
    edge_margin_mm: margin.ok ? margin.value : 1,
    component_gap_mm: gap.ok ? gap.value : 0.25,
    fixed_components: c.fixed_components.split(/[\s,]+/).filter(Boolean),
    outline_fixed: c.outline_fixed,
    keep_locked_fixed: c.keep_locked_fixed,
    keep_connectors_fixed: c.keep_connectors_fixed,
    allow_rotation: c.allow_rotation,
    requirements: c.requirements.filter((r) => r.kind.trim()).map((r) => ({ kind: r.kind.trim(), description: r.description.trim(), hard: r.hard })),
  };
  if (width.ok && width.value !== undefined) body.max_board_width_mm = width.value;
  if (height.ok && height.value !== undefined) body.max_board_height_mm = height.value;
  return { ok: true, value: body };
}

/** Weights for the objectives that have one; none when every box is empty. */
export function weightsBody(weights: Partial<Record<Objective, string>>, objectives: Set<Objective>): Parsed<Partial<Record<Objective, number>> | undefined> {
  const out: Partial<Record<Objective, number>> = {};
  for (const o of objectives) {
    const text = weights[o]?.trim();
    if (!text) continue;
    const n = Number(text);
    if (!Number.isFinite(n) || n < 0 || n > 1000) return { ok: false, error: "Weights must be between 0 and 1000." };
    out[o] = n;
  }
  return { ok: true, value: Object.keys(out).length ? out : undefined };
}

export function buildQuantityBody(text: string): Parsed<number | undefined> {
  return num("Build quantity", text, 1, 1_000_000, true) as Parsed<number | undefined>;
}

function Check({ label, checked, onChange, hint }: { label: string; checked: boolean; onChange: (v: boolean) => void; hint?: string }) {
  return (
    <label className="flex items-center gap-1.5 text-sm" title={hint}>
      <input type="checkbox" checked={checked} onChange={(e) => onChange(e.target.checked)} />
      {label}
    </label>
  );
}

function NumberField({ label, value, onChange, placeholder }: { label: string; value: string; onChange: (v: string) => void; placeholder?: string }) {
  return (
    <label className="flex flex-col gap-1 text-xs font-medium">
      {label}
      <Input inputMode="decimal" value={value} placeholder={placeholder} onChange={(e) => onChange(e.target.value)} className="w-28 font-normal" />
    </label>
  );
}

export function ConstraintsForm({ value, onChange }: { value: ConstraintsInput; onChange: (v: ConstraintsInput) => void }) {
  const set = <K extends keyof ConstraintsInput>(k: K, v: ConstraintsInput[K]) => onChange({ ...value, [k]: v });
  const setReq = (i: number, patch: Partial<Requirement>) => set("requirements", value.requirements.map((r, j) => (j === i ? { ...r, ...patch } : r)));
  return (
    <details className="rounded-md border border-border px-3 py-2">
      <summary className="cursor-pointer text-sm font-medium">Constraints</summary>
      <div className="mt-3 space-y-3">
        <p className="text-xs text-muted">Hard constraints: a candidate that breaks one fails validation. A requirement VIA can&apos;t evaluate is recorded as unverified and keeps the candidate from being accepted.</p>
        <div className="flex flex-wrap gap-3">
          <NumberField label="Edge margin (mm)" value={value.edge_margin_mm} onChange={(v) => set("edge_margin_mm", v)} />
          <NumberField label="Component gap (mm)" value={value.component_gap_mm} onChange={(v) => set("component_gap_mm", v)} />
          <NumberField label="Max width (mm)" value={value.max_board_width_mm} onChange={(v) => set("max_board_width_mm", v)} placeholder="none" />
          <NumberField label="Max height (mm)" value={value.max_board_height_mm} onChange={(v) => set("max_board_height_mm", v)} placeholder="none" />
          <label className="flex min-w-48 flex-1 flex-col gap-1 text-xs font-medium">
            Parts that must not move (references)
            <Input value={value.fixed_components} placeholder="e.g. J1, U3" onChange={(e) => set("fixed_components", e.target.value)} className="font-mono font-normal" />
          </label>
        </div>
        <div className="flex flex-wrap gap-x-4 gap-y-1.5">
          <Check label="Keep the outline" checked={value.outline_fixed} onChange={(v) => set("outline_fixed", v)} hint="The board outline must not change" />
          <Check label="Keep locked parts" checked={value.keep_locked_fixed} onChange={(v) => set("keep_locked_fixed", v)} hint="Parts locked in KiCad don't move" />
          <Check label="Keep connectors and mounting holes" checked={value.keep_connectors_fixed} onChange={(v) => set("keep_connectors_fixed", v)} />
          <Check label="Allow rotating parts" checked={value.allow_rotation} onChange={(v) => set("allow_rotation", v)} hint="Placement may turn unlocked top-side parts by quarter turns" />
        </div>
        <div className="space-y-1.5">
          <h4 className="text-xs font-medium">Requirements VIA can&apos;t evaluate</h4>
          <datalist id="requirement-kinds">{REQUIREMENT_KINDS.map((k) => <option key={k} value={k} />)}</datalist>
          {value.requirements.map((r, i) => (
            <div key={i} className="flex flex-wrap items-center gap-2">
              <Input list="requirement-kinds" aria-label="Requirement kind" value={r.kind} placeholder="kind" onChange={(e) => setReq(i, { kind: e.target.value })} className="w-48 font-mono" />
              <Input aria-label="Requirement description" value={r.description} placeholder="what it must satisfy" onChange={(e) => setReq(i, { description: e.target.value })} className="min-w-48 flex-1" />
              <Check label="Hard" checked={r.hard} onChange={(v) => setReq(i, { hard: v })} hint="A hard requirement VIA can't verify stops a candidate from being validated" />
              <Button size="sm" variant="ghost" aria-label="Remove requirement" onClick={() => set("requirements", value.requirements.filter((_, j) => j !== i))}><X /></Button>
            </div>
          ))}
          <Button size="sm" variant="ghost" onClick={() => set("requirements", [...value.requirements, { kind: "", description: "", hard: true }])}><Plus /> Add requirement</Button>
        </div>
      </div>
    </details>
  );
}

export function WeightsForm({ objectives, labels, value, onChange }: { objectives: Objective[]; labels: Record<string, string>; value: Partial<Record<Objective, string>>; onChange: (v: Partial<Record<Objective, string>>) => void }) {
  if (objectives.length < 2) return null;
  return (
    <details className="rounded-md border border-border px-3 py-2">
      <summary className="cursor-pointer text-sm font-medium">Preference weights</summary>
      <div className="mt-3 space-y-2">
        <p className="text-xs text-muted">Optional. Weights only change the order candidates are listed in, by how much they improve each objective. They never change validation, constraints or the Pareto set. Leave empty for no ordering.</p>
        <div className="flex flex-wrap gap-3">
          {objectives.map((o) => (
            <NumberField key={o} label={labels[o] ?? o} value={value[o] ?? ""} placeholder="0-1000" onChange={(v) => onChange({ ...value, [o]: v })} />
          ))}
        </div>
      </div>
    </details>
  );
}

export function PricingForm({ projectId, isOwner, value, onChange }: { projectId: string; isOwner: boolean; value: string; onChange: (v: string) => void }) {
  const client = useApi();
  const status = useAsync((s) => client.optimization.supplierStatus(s), [client]);
  const consent = useAsync((s) => client.optimization.supplierConsent(projectId, s), [client, projectId]);
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  async function change(grant: boolean) {
    setBusy(true);
    setError(null);
    try {
      if (grant) consent.setData(await client.optimization.grantSupplierConsent(projectId));
      else {
        await client.optimization.revokeSupplierConsent(projectId);
        consent.setData({ granted: false, granted_at: null, policy_version: consent.data?.policy_version ?? "" });
      }
    } catch (err) {
      setError(errorMessage(err));
    } finally {
      setBusy(false);
    }
  }

  let body;
  if (!status.data || !consent.data) body = <p className="text-xs text-muted">Checking supplier pricing…</p>;
  else if (!status.data.configured) body = <p className="text-xs text-muted">Supplier pricing isn&apos;t set up on this server. It needs a Mouser API key (MOUSER_API_KEY) in the server&apos;s environment.</p>;
  else if (!consent.data.granted) {
    body = (
      <div className="space-y-2">
        <p className="text-xs text-muted">Pricing looks up your BOM&apos;s manufacturer part numbers on Mouser. Only the part numbers are sent, and only once the project owner allows it.</p>
        {isOwner ? <Button size="sm" variant="outline" disabled={busy} onClick={() => void change(true)}>Allow Mouser lookups for this project</Button> : <p className="text-xs text-muted">Ask the project owner to allow it.</p>}
      </div>
    );
  } else {
    body = (
      <div className="space-y-2">
        <label className="flex flex-col gap-1 text-xs font-medium">
          Boards to build
          <Input inputMode="numeric" value={value} placeholder="e.g. 25" onChange={(e) => onChange(e.target.value)} className="w-28 font-normal" />
        </label>
        <p className="text-xs text-muted">Leave empty to skip pricing. Prices are Mouser&apos;s listings at the time of the run, not a quote. Only listings with exactly the same part number are used.</p>
        {isOwner ? <Button size="sm" variant="ghost" disabled={busy} onClick={() => void change(false)}>Stop allowing lookups</Button> : null}
      </div>
    );
  }
  return (
    <details className="rounded-md border border-border px-3 py-2" open={Boolean(status.data?.configured && consent.data?.granted)}>
      <summary className="cursor-pointer text-sm font-medium">Supplier pricing (Mouser)</summary>
      <div className="mt-3">
        {body}
        {error ? <p className="mt-1 text-xs text-danger">{error}</p> : null}
      </div>
    </details>
  );
}
