# VIA Optimize: architecture

Package `services/optimization` (`via_opt`, pure Python, no I/O). API glue in `apps/api/src/via_api/{services/optimizer.py,routes/optimization.py,suppliers/}`. Frontend in `apps/web/components/analysis/optimize-*.tsx`.

## Principles
- The normalized PCB model (`via_pcb`) is the only design representation. `via_opt` reads it and never mutates it: every candidate is applied to a deep copy (`changes.apply`).
- The original revision is never modified. A candidate becomes a revision only through the change-set flow (`CHANGE_MANAGEMENT.md`): accept, create change set, apply (`pcb_export` job), new child revision, with rollback and lineage.
- Everything numeric is computed by deterministic code. AI is not used in this package.
- Nothing is applied automatically. Accepting records a decision; applying is a separate, explicit step.

## Modules
| File | Role |
|---|---|
| `constraints.py` | user constraints and declared requirements |
| `rules.py` | hard-constraint registry; returns `satisfied / violated / unverified / not_applicable` per constraint |
| `objectives.py` | baseline and candidate metrics |
| `analysis.py` | area and margin analysis (reports, not candidates) |
| `algorithms/outline.py`, `copper.py`, `placement.py` | candidate generators |
| `bom.py` | BOM extraction and the cheapest / fastest / balanced planner |
| `validation.py` | re-runs VIA's checks on the modified copy; sets validation status |
| `ranking.py`, `comparison.py` | weighted display order; Pareto front |
| `lifecycle.py` | derived candidate lifecycle |
| `modules.py` | `ModuleSpec` declarations (what each module can and cannot do) |
| `report.py` | JSON and markdown run report from stored data |
| `engine.py` | pipeline, candidate hashing, progress callback |
| `changes.py`, `export.py`, `cli.py` | change model, KiCad export, sandbox entry point |

## Pipeline
1. Baseline metrics, area analysis, margin analysis.
2. Generators produce change sets within the constraints.
3. Each candidate is applied to a copy, measured, and passed through `rules.evaluate` and `validation`.
4. Candidates are compared (Pareto) and optionally ordered by the user's weights.
5. If a build quantity was given and consent exists, the worker prices the BOM from Mouser (outside the sandbox: the sandbox has no network).
6. The run summary, candidates and (on request) the report are stored and served.

## Execution
Runs are `analysis_runs` (`kind = pcb_optimization`) on the shared worker lifecycle (heartbeat, reaper, retries, `worker_lost`). The optimizer runs in the sandbox as `python -I -m via_opt.cli`. The current phase is written to `result_summary["phase"]`; there are no progress percentages because the time is not predictable.

## Security
- Authorization is enforced in the API service layer for every read and write; project-scoped data returns 404 without access.
- Supplier lookup needs a project-owner consent (`supplier_lookup`), only manufacturer part numbers leave the server, and the key (`MOUSER_API_KEY`) is never logged or returned.
- Uploaded files are never executed or sent anywhere by this feature.
