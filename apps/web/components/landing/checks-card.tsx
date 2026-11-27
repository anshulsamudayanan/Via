"use client";

import { LiquidGlass } from "@via/ui";
import { CircuitBoard, Cpu, Factory, Network, Route, ShieldCheck, Zap } from "lucide-react";
import type { ReactNode } from "react";

/*
 * "What VIA checks": the deterministic check families as they exist in the analysis engine
 * (services/pcb-engine/src/via_pcb/analysis/checks/). Counts are the number of checks in each
 * family, a product fact; keep this list in step with the registry.
 */
const FAMILIES: { icon: ReactNode; name: string; detail: string; checks: number }[] = [
  { icon: <Factory />, name: "Manufacturing", detail: "track width, vias, holes, copper spacing, edge clearance, silkscreen vs your fab profile", checks: 7 },
  { icon: <Network />, name: "Connectivity", detail: "unrouted connections, single-pad nets, pads without a net", checks: 3 },
  { icon: <Route />, name: "Routing and rules", detail: "net-class widths, detours, layer usage, design-rule source", checks: 4 },
  { icon: <Zap />, name: "Power and signal", detail: "IPC-2221 current capacity, decoupling distance, microstrip impedance", checks: 3 },
  { icon: <Cpu />, name: "Placement", detail: "connector edge access, component rotation", checks: 2 },
  { icon: <CircuitBoard />, name: "Board and import", detail: "outline, unused space, import warnings", checks: 3 },
  { icon: <ShieldCheck />, name: "KiCad DRC", detail: "KiCad's own design rule check, run on the uploaded board", checks: 1 },
];

export function ChecksCard() {
  return (
    <LiquidGlass variant="regular" as="section" aria-labelledby="checks-card-title" className="rounded-[28px] p-5">
      <h2 id="checks-card-title" className="font-display text-[20px] font-semibold tracking-[-0.02em] text-foreground">
        What VIA checks
      </h2>
      <p className="mt-0.5 text-[12.5px] text-subtle">23 deterministic checks, each with measured evidence</p>
      <ul className="mt-4 space-y-1">
        {FAMILIES.map((f) => (
          <li key={f.name} className="flex items-center gap-3 rounded-2xl px-1.5 py-1.5 transition-colors hover:bg-surface-hover">
            <span className="flex size-9 shrink-0 items-center justify-center rounded-xl border border-border bg-surface text-accent [&_svg]:size-4" aria-hidden="true">
              {f.icon}
            </span>
            <div className="min-w-0 flex-1">
              <p className="text-[13.5px] font-medium text-foreground">{f.name}</p>
              <p className="truncate text-[12px] text-subtle" title={f.detail}>
                {f.detail}
              </p>
            </div>
            <span className="shrink-0 font-mono text-[11px] text-muted tabular-nums" aria-label={`${f.checks} ${f.checks === 1 ? "check" : "checks"}`}>
              {f.checks}
            </span>
          </li>
        ))}
      </ul>
    </LiquidGlass>
  );
}
