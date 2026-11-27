/*
 * What one finding looks like. Field names and wording follow the real `mfg_copper_spacing` check
 * (rule `copper_spacing_too_small`); the numbers and object ids are illustrative, and the card says so.
 */

import { Glass } from "@via/ui";

const ROWS: { k: string; v: React.ReactNode }[] = [
  { k: "check", v: <><span className="text-foreground">mfg_copper_spacing</span> <span className="text-subtle">v1.0.0</span></> },
  { k: "rule", v: <span className="text-foreground">copper_spacing_too_small</span> },
  { k: "source", v: <>via_deterministic <span className="text-subtle">·</span> <span className="text-success">verified</span></> },
  {
    k: "objects",
    v: (
      <span className="flex flex-col">
        <span>track <span className="text-foreground">#4f1c…a2</span> <span className="text-subtle">net</span> GND <span className="text-subtle">layer</span> F.Cu</span>
        <span>pad&nbsp;&nbsp; <span className="text-foreground">U1.7</span>&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;<span className="text-subtle">net</span> SIG <span className="text-subtle">layer</span> F.Cu</span>
      </span>
    ),
  },
  { k: "measured", v: <><span className="text-subtle">Smallest gap</span> <span className="font-medium text-danger">0.118 mm</span></> },
  { k: "required", v: <><span className="text-subtle">Minimum clearance</span> <span className="text-foreground">0.150 mm</span></> },
  { k: "location", v: <>(171.40, 103.25) mm <span className="text-subtle">· F.Cu</span></> },
];

export function SampleFinding() {
  return (
    <Glass as="figure" variant="regular" sheen className="overflow-hidden rounded-[28px] shadow-[0_40px_100px_-36px_var(--landing-glow)]">
      <div className="flex items-center gap-2 border-b border-border px-5 py-3">
        <span className="rounded-full bg-danger-soft px-2 py-0.5 text-[10px] font-semibold uppercase tracking-wide text-danger">high</span>
        <span className="truncate text-[13px] font-medium text-foreground">Copper spacing below 0.150 mm: GND / SIG</span>
        <span className="ml-auto shrink-0 rounded-full border border-border px-2 py-0.5 text-[10px] font-medium uppercase tracking-wide text-subtle">Example</span>
      </div>
      {/* A scrim under the values keeps small mono text above 4.5:1 whatever the glass shows. */}
      <dl className="grid grid-cols-[5.5rem_minmax(0,1fr)] gap-x-3 gap-y-2 bg-[var(--via-scrim)] px-5 py-5 font-mono text-[12px] leading-relaxed text-muted sm:grid-cols-[6.5rem_minmax(0,1fr)]">
        {ROWS.map((r) => (
          <div key={r.k} className="contents">
            <dt className="text-subtle">{r.k}</dt>
            <dd className="min-w-0 break-words sm:whitespace-nowrap">{r.v}</dd>
          </div>
        ))}
      </dl>
      <figcaption className="border-t border-border px-5 py-2.5 text-[11px] text-subtle">
        Example finding with illustrative values. Every real finding names the exact objects and the measured value against the rule.
      </figcaption>
    </Glass>
  );
}
