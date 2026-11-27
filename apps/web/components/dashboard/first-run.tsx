import { Button } from "@via/ui";
import { Plus } from "lucide-react";
import type { ReactNode } from "react";

/** A bare two-layer board: outline, mounting holes, an IC and passives, routed traces and vias. Decorative. */
function BoardIllustration() {
  return (
    <svg viewBox="0 0 240 160" aria-hidden="true" className="h-auto w-full max-w-[380px]" fill="none">
      <defs>
        <pattern id="fr-grid" width="10" height="10" patternUnits="userSpaceOnUse">
          <path d="M10 0H0V10" stroke="var(--via-border)" strokeWidth="0.5" />
        </pattern>
      </defs>
      <rect x="0.5" y="0.5" width="239" height="159" fill="url(#fr-grid)" opacity="0.7" />
      {/* Board outline (Edge.Cuts) */}
      <rect x="30" y="22" width="180" height="116" rx="6" fill="var(--via-surface-raised)" stroke="var(--via-border-strong)" />
      {[
        [40, 32],
        [200, 32],
        [40, 128],
        [200, 128],
      ].map(([cx, cy]) => (
        <circle key={`${cx}-${cy}`} cx={cx} cy={cy} r="4" fill="var(--via-background)" stroke="var(--via-border-strong)" />
      ))}
      {/* Back-layer traces, dimmer */}
      <g stroke="var(--via-border-strong)" strokeWidth="1.5" strokeLinecap="round">
        <path d="M62 112H96L108 100H150" />
        <path d="M160 52V74L176 90V112" />
      </g>
      {/* Front-layer traces in the accent */}
      <g stroke="var(--via-accent)" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round" opacity="0.9">
        <path d="M100 62H78L70 54H58" />
        <path d="M100 70H84V88H62" />
        <path d="M140 62H160V52" />
        <path d="M140 78H150V100" />
        <path d="M120 90V112H96" />
      </g>
      {/* IC: body + pads */}
      <rect x="100" y="54" width="40" height="36" rx="2" fill="var(--via-surface-sunken)" stroke="var(--via-border-strong)" />
      <circle cx="106" cy="60" r="1.5" fill="var(--via-subtle)" />
      {[58, 66, 74, 82].map((y) => (
        <g key={y} fill="var(--via-subtle)">
          <rect x="95" y={y - 1.5} width="5" height="3" rx="0.5" />
          <rect x="140" y={y - 1.5} width="5" height="3" rx="0.5" />
        </g>
      ))}
      {/* Passives */}
      {(
        [
          [50, 50],
          [50, 84],
          [168, 112],
        ] as const
      ).map(([x, y]) => (
        <g key={`${x}-${y}`}>
          <rect x={x} y={y} width="12" height="7" rx="1" fill="var(--via-surface-sunken)" stroke="var(--via-border-strong)" />
          <rect x={x} y={y} width="3" height="7" fill="var(--via-subtle)" />
          <rect x={x + 9} y={y} width="3" height="7" fill="var(--via-subtle)" />
        </g>
      ))}
      {/* Vias */}
      {[
        [160, 52],
        [150, 100],
        [62, 112],
        [176, 90],
      ].map(([cx, cy]) => (
        <circle key={`${cx}-${cy}`} cx={cx} cy={cy} r="2.6" fill="var(--via-surface-raised)" stroke="var(--via-accent)" strokeWidth="1.2" />
      ))}
    </svg>
  );
}

function Step({ n, title, children }: { n: number; title: string; children: ReactNode }) {
  return (
    <li className="flex gap-3">
      <span className="mt-0.5 flex size-5 shrink-0 items-center justify-center rounded-full border border-border-strong font-mono text-[10px] text-muted">{n}</span>
      <div className="min-w-0">
        <p className="text-[13px] font-medium text-foreground">{title}</p>
        <p className="text-xs leading-relaxed text-muted">{children}</p>
      </div>
    </li>
  );
}

/** First-run state for an account with no projects: what VIA needs, in order, and the one action that starts it. */
export function FirstRun({ newProject }: { newProject: (trigger: ReactNode) => ReactNode }) {
  return (
    <section aria-labelledby="first-run-title" className="overflow-hidden rounded-lg border border-border bg-surface">
      <div className="grid items-center gap-8 px-6 py-8 md:grid-cols-[minmax(0,1fr)_minmax(0,400px)] md:px-10 md:py-12">
        <div className="max-w-md">
          <p className="font-mono text-[11px] uppercase tracking-[0.08em] text-subtle">No projects yet</p>
          <h2 id="first-run-title" className="mt-2 font-display text-[2rem] leading-[1.1] text-foreground">
            Start with a board.
          </h2>
          <p className="mt-2 text-[13px] leading-relaxed text-muted">
            Projects are private by default: only you and the people you invite can see them.
          </p>
          <ol className="mt-6 space-y-4">
            <Step n={1} title="Create a project">
              A workspace for one board or product.
            </Step>
            <Step n={2} title="Upload a KiCad board">
              A <code className="font-mono text-foreground">.kicad_pcb</code> file, or a zipped project with its <code className="font-mono text-foreground">.kicad_pro</code>{" "}
              design rules.
            </Step>
            <Step n={3} title="Run an analysis">
              Deterministic checks that name the exact objects, the measured value and the rule.
            </Step>
          </ol>
          <div className="mt-6">
            {newProject(
              <Button variant="primary">
                <Plus /> New project
              </Button>,
            )}
          </div>
        </div>
        <div className="flex justify-center md:justify-end">
          <BoardIllustration />
        </div>
      </div>
    </section>
  );
}
