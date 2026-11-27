"use client";

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

/** The check families with their counts, as a plain list for the checks card in the feature grid. */
export function ChecksCard() {
  const total = FAMILIES.reduce((n, f) => n + f.checks, 0);
  return (
    <div className="w-full">
      <p className="px-2 font-mono text-[12px] text-subtle">{total} checks in {FAMILIES.length} families</p>
      <ul className="mt-2 space-y-0.5">
        {FAMILIES.map((f) => (
          <li key={f.name} className="flex items-center gap-3 rounded-lg px-2 py-1.5">
            <span className="flex size-4 shrink-0 text-muted [&_svg]:size-4" aria-hidden="true">
              {f.icon}
            </span>
            <div className="min-w-0 flex-1">
              <p className="text-[14px] text-foreground">{f.name}</p>
              <p className="truncate text-[12px] text-subtle" title={f.detail}>
                {f.detail}
              </p>
            </div>
            <span className="shrink-0 font-mono text-[12px] tabular-nums text-muted" aria-label={`${f.checks} ${f.checks === 1 ? "check" : "checks"}`}>
              {f.checks}
            </span>
          </li>
        ))}
      </ul>
    </div>
  );
}
