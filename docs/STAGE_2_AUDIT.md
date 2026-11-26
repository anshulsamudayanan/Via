# Stage 2 Audit: VIA Core Foundation

Date: 2026-11-26. Audited commit: `6083195` (`main`, identical to `origin/main`; working tree clean).
Purpose: establish what Stage 2 (PCB Intelligence & Optimization) can safely build on, what must
be fixed first, and the milestone plan. Nothing in this document has been implemented yet.

## 1. How the audit was done

- Read `CLAUDE.md` and every document in `docs/`; reviewed the PCB engine, the API (models,
  migrations, services, routes, jobs, parser sandbox), the AI engine, the viewer and the CI workflow.
- Ran the complete test suite on a fresh Docker Compose stack in this environment:
  - Python: **236 passed, 1 skipped** (`RLIMIT_NPROC` is not enforced for root; runs in CI).
    Covers 10 real KiCad boards (5.1–9.0) and real Postgres, Redis and MinIO.
  - Frontend: **82 passed** (62 web, 12 API client, 8 UI); lint and types clean.
  - Playwright end to end against the stack: **4 passed**.
  - CI on `main`: green (all three jobs).
- Ran experiments to answer the questions Stage 2 depends on (results in §5 and §6):
  1. KiCad's real DRC (`kicad-cli` 9.0.6, official image) on our boards.
  2. KiCad's DRC with and without the project's `.kicad_pro` rules.
  3. A `pcbnew` load → save round trip and a footprint move.
  4. Killing the worker in the middle of a parse.

## 2. What works (verified)

| Area | State |
|---|---|
| KiCad import | `.kicad_pcb` from KiCad 5.1–9.0 parsed into `PCBDesign` (schema 1.0.0). Counts, geometry and pad transforms checked against independent scans of 10 real boards. |
| Pipeline | Upload (size/type/sniff/SHA-256/duplicates), object storage, RQ worker, credential-free rlimited parser subprocess, gzipped normalized JSON plus queryable rows, revisions, failure reporting. |
| Accounts, projects, sharing | Sessions, CSRF, rate limits, audit log; private-by-default projects; org and project roles independent; route-wide security regression suite. |
| Viewer | Canvas 2D from the normalized model through a render model: layers, components, selection, search, zoom/pan, snapshot mode for > 40k primitives. |
| AI foundation | Provider interface, disabled default, Anthropic adapter (optional), per-project external-AI consent, bounded consent-gated `ProjectContext`. No feature calls a model. |
| Data model | 18 tables incl. `analysis_runs` (only `kind = pcb_import` used) and `data_consents`; migrations with parity test. |

## 3. Critical bug found: worker crash leaves revisions stuck

**Reproduced:** uploaded the 47 MB stress board, killed the worker container (`SIGKILL`) while
the revision was `processing`, restarted it. Almost 4 minutes later, well past the job's
180-second timeout, the revision was still `processing`: no error, no retry, and the UI polling
indefinitely. Whether RQ's periodic registry cleanup eventually fails the job and runs the
callback is checked in M1; either way, minutes of silent limbo with no retry is not acceptable.

**Cause:** the RQ `on_failure` callback runs only when the work-horse fails in a way the parent
worker observes; if the whole worker process dies, nothing marks the revision failed or requeues
the job. There is no stale-job reaper.

**Why it matters for Stage 2:** analysis and optimization jobs are longer and more numerous than
imports; the same failure would strand them.

**Fix (first task of Milestone 1):** a job-lifecycle layer shared by all job kinds. It has:
- heartbeat timestamps on running work;
- a periodic reaper in the worker that fails or requeues work whose heartbeat is stale;
- a bounded retry count for retry-safe failures;
- idempotent job ids, which already exist for imports.

A test kills a job mid-run and asserts recovery.

## 4. Incomplete functionality and technical debt

| # | Item | Impact on Stage 2 | Plan |
|---|---|---|---|
| D1 | Stuck jobs after worker crash (§3) | Blocks reliable analysis jobs | Fix in M1 |
| D2 | **Only `.kicad_pcb` is imported, not the project.** KiCad 6+ keeps design rules and net classes in `.kicad_pro` (and custom rules in `.kicad_dru`) | DRC without them is wrong (see §5: 54 false violations on a clean board) | Project import in M1 |
| D3 | Normalized objects other than footprints have **no stable ids** (tracks, vias, zones, pads) | Findings can't point at exact objects; KiCad DRC results (which reference UUIDs) can't be mapped; change sets can't target objects | Add ids in M1 (schema 1.1.0) |
| D4 | Model gaps: `locked` flag ignored; no stackup; no texts; no filled zone polygons; no pad corner radius or custom pad primitives; no pad mask/paste margins; no keep-out rule details | Fixed-position constraints, impedance/SI, silkscreen and zone checks are impossible or approximate | Add `locked`, stackup, keep-out rules, pad margins in M1; filled zones come from KiCad (DRC refills); texts deferred |
| D5 | The S-expression tree keeps **no source positions** | Lossless export by patching the original file needs spans | Add spans in M6 (export) |
| D6 | Forwarded-IP trust depends on the reverse proxy (CP6 finding) | Unchanged for local use; launch item | Not Stage 2 scope unless you want it |
| D7 | No email provider; no presigned uploads; Next.js buffers uploads | Unchanged | Not Stage 2 scope |
| D8 | Parser peak memory ≈ 35× file size | Analysis adds memory on top | Analysis runs on the stored normalized JSON, not by re-parsing; set limits per job |
| D9 | Viewer computes on the main thread | Overlays, net highlighting and comparisons will add cost | Web Worker for render-model building and hit-testing in M7 |
| D10 | `analysis_runs` is generic but has no link to findings, rule set, profile or engine versions beyond `engine_version` | Needed for provenance | Extend in M2 |
| D11 | Still no permissively licensed real boards committed (CC BY-SA demos only, fetched on demand) | Regression fixtures for Stage 2 | Synthetic edge-case boards (original work) plus a search for CC0/CC-BY/MIT/CERN-OHL-P boards; needs your licence policy (unchanged from CP2) |
| D12 | Workspace "Analysis" tab is an honest coming-soon panel | Replaced in M7 | — |

No other Stage 1 functionality was found to be unreliable. Rewriting working components is not planned.

## 5. KiCad integration: measured facts

**Real DRC is available headless.** The official image `kicad/kicad:9.0.6`
(`sha256:3371f20b…825d9`, Debian 12, 2.25 GB) runs
`kicad-cli pcb drc --format json --severity-all --units mm` with no network. Each violation
carries a type, severity, description and, for each affected object, its UUID and position.

| Board | Time | Result without `.kicad_pro` | With the project's `.kicad_pro` |
|---|---|---|---|
| KiCad 9 `video` demo (8,740 tracks) | 3.7 s | 25 copper-edge errors, 20 silk-edge and 9 silk-over-copper warnings, 189 library warnings | **0** design violations (only the 189 library warnings) |
| KiCad 5 `pic_programmer` | 1.7 s | 2 starved thermals, 51 silkscreen, 57 library warnings | not measured |
| VIA reference board (hand-authored) | 1.2 s | 2 shorts, 6 clearance, 3 hole clearance, 4 mask bridge | n/a (no project file) |

Conclusions:
- **DRC without the project's rules produces false findings.** VIA must import projects
  (D2). Results must state which rule source was used, and boards imported without a project
  file must be labelled "KiCad default rules".
- `lib_footprint_issues`/`lib_footprint_mismatch` warnings come from library tables not being
  configured in the container. They describe the environment, not the design, so they will be
  suppressed and reported as "not checked".
- Our hand-authored reference board really has shorts and clearance errors. Engineering tests
  for the parser stay as they are; Stage 2 will add separate, deliberately clean and
  deliberately faulty synthetic boards with hand-derived expectations.
- KiCad refills zones during DRC, so zone-related checks come from KiCad. VIA doesn't
  reimplement copper pours.

**Round trip through KiCad's own writer (`pcbnew` Python API 9.0.6):** load → save without
changes on the KiCad 9 `video` board kept everything except one obsolete plot setting
(`plotinvisibletext`): one line out of 5.8 MB, which would have been a *silent* loss. Moving
U1 by 1 mm changed exactly 4 lines. However, `pcbnew` always writes the **KiCad 9 format**, so
saving a KiCad 6–8 board this way upgrades it, and older KiCad versions can no longer open it.

**Licensing:** KiCad is GPL-3.0. Running `kicad-cli`/`pcbnew` as a separate program in its own
container, without linking it into VIA, is ordinary aggregation. Your decision is still needed
before shipping it (§8, decision 1).

**Security:** KiCad's C++ parser is a much larger attack surface than our pure-Python parser.
KiCad must run in its own container with:
- no credentials (empty environment);
- no network;
- CPU/memory/time limits;
- a non-root user.

The worker passes files in and reads reports out.

## 6. PCB model limitations relevant to analysis

| Needed for | Model today | Consequence |
|---|---|---|
| Object-level findings | Footprint UUID only | Add ids for pads (footprint UUID + pad number + index), tracks, vias, zones (KiCad UUIDs; synthetic stable ids when absent, e.g. KiCad 5 segments) |
| Placement constraints | No `locked` | Add `locked`; "fixed component" constraints default to locked footprints |
| Impedance / signal integrity | No stackup | Parse `(setup (stackup ...))` when present; without it, impedance is "not computable" and never guessed |
| Current capacity / thermal | No current or power data anywhere | Only with user-provided per-net requirements (IPC-2221/2152 formulas, assumptions stated); otherwise thermal checks are limited to geometric heuristics labelled as such |
| Decoupling proximity | Values and nets exist; no symbol/pin function data | Heuristic: capacitors sharing a power net and a ground net with an IC's pads. Labelled a heuristic, confidence < 1 |
| Clearances | Exact geometry for tracks, vias, pads (rectangles approximate rounded/custom pads); zone outlines only | Authoritative clearance/short checks come from KiCad DRC; VIA's own geometry checks are labelled and limited to what the model represents exactly |
| Export | Lossy by design (texts, 3D, groups, dimensions not modelled) | **Export never regenerates a file from `PCBDesign`.** Changes are applied to the original source (see M6) |

## 7. Integration opportunities

1. **KiCad DRC** (`kicad-cli pcb drc`): authoritative rule checks with UUID mapping (M3).
2. **KiCad as validator and writer**: load the changed file in KiCad (parse check), re-run DRC, optionally save through `pcbnew` (M6).
3. **KiCad project rules**: parse `.kicad_pro` net classes and constraints into `DesignConstraints` so VIA's own checks and the optimizer use the designer's real rules (M1).
4. **IPC-2221/2152 formulas** for current capacity, given user inputs (M3), and stackup-based impedance estimates when a stackup exists (M3). Both are labelled "calculated estimate".
5. **Freerouting** (Specctra DSN via `pcbnew`): possible later for re-routing optimization candidates. Not planned for Stage 2; noted for VIA Optimize later.
6. **Existing AI foundation**: provider interface, consent and `ProjectContext` extend directly to explanations and reviews (M4).

## 8. Decisions needed from you

1. **KiCad in the stack.** I recommend a separate `eda-worker` Compose service built from `kicad/kicad:9.0.6`, pinned by digest. It is ~2.3 GB, GPL-3, and runs as a separate program. It would have its own RQ queue and run KiCad in a credential-free, network-less subprocess.
   - It's optional at runtime: without it, VIA still runs its own checks and says KiCad DRC is unavailable.
   - OK to add this image and its licence obligations (shipping KiCad's licence and source offer if we ever distribute images)?
2. **Export strategy.** I recommend **patching the original file in place** by UUID, using source spans. This keeps the original KiCad version, formatting and every unmodelled element, and produces a minimal diff. Each export is then validated: KiCad loads it, KiCad DRC runs, VIA re-parses it and checks that only the intended changes happened.
   - The alternative is saving through `pcbnew`. It's simpler and native, but it upgrades the file to KiCad 9 format, and older KiCad versions can't open it.
   - Patch first, with `pcbnew` saving only as an explicit opt-in?
3. **Project import format.** I recommend accepting a `.zip` of the KiCad project, from which VIA takes `.kicad_pcb`, `.kicad_pro` and `.kicad_dru` (other files are ignored, and archive limits are enforced against zip bombs and path traversal). A bare `.kicad_pcb` would still work, labelled "default rules".
4. **Manufacturing profiles.** I won't invent manufacturer capabilities.
   - I propose shipping two VIA profiles, *Conservative* and *Advanced*. Their values are documented as VIA defaults, not any manufacturer's claims.
   - Users can also create their own profiles.
   - Named manufacturer profiles would only be added with a cited, dated public source. Is that acceptable, or do you have specific manufacturers in mind?
5. **AI provider for development.** The Anthropic adapter exists, but real calls need an API key in the environment plus per-project consent.
   - Tests use a deterministic fake provider, and AI output is always labelled and schema-validated.
   - Do you want to provide a key for manual testing?
6. **Optimization scope (honest framing).** Without an autorouter, moving routed components breaks their connections. Stage 2 optimization would therefore:
   - generate placement candidates on ratsnest metrics, explicitly marked "requires re-routing";
   - generate *validatable* candidates such as board-outline reduction, track widening where clearance allows, and via/drill standardization;
   - estimate relative cost with a documented cost model (an estimate, never a quote).

   Agree?

## 9. Proposed plan: 8 milestones, each a checkpoint you approve

Every milestone ends with lint, types, the full Stage 1 and Stage 2 test suites, a security check, doc updates, a commit and a push. Then I stop for your approval.

| M | Scope | Key deliverables | Acceptance |
|---|---|---|---|
| **1** | Audit fixes and PCB model 1.1 | Job lifecycle (heartbeat, reaper, retries) with a crash test. Stable object ids. `locked`, stackup, keep-out rules, pad margins. Project zip import with `.kicad_pro`/`.kicad_dru` rule parsing into `DesignConstraints`, archive safety tests. Schema 1.1.0 with older stored designs still readable. | Crash recovery test passes. Ids are stable across re-parses. Real `video` project imports with its net classes. All Stage 1 tests green. |
| **2** | Findings and analysis framework | `services/pcb-engine/src/via_pcb/analysis/` (engine, registry, context, check interface, finding schema, severity, evidence). DB: `analysis_runs` extended, `analysis_findings`, `finding_evidence`, `finding_reviews` (reviewed/dismissed with reason, history kept). Analysis job on the worker. APIs: start, status, list/filter/sort/search findings, review/dismiss, compare across revisions. Results tied to the exact revision plus parser, engine, rule-set and profile versions; nothing overwritten. | A trivial check runs end to end via the API. Security suite covers the new routes automatically. |
| **3** | Deterministic analysis and KiCad DRC | `eda-worker` with KiCad DRC, mapped to findings by UUID, source "KiCad DRC". VIA checks: geometry, board outline, connectivity graph (islands, unrouted pads, single-pad nets, dangling tracks/vias), placement (density, grouping, orientation, connector edge access, decoupling heuristic), manufacturing (profiles: widths, spacing, drills, annular rings, copper-to-edge, silk), routing (layer usage, via count, detours vs. direct distance), power/thermal estimates with user inputs only. | Each check tested on synthetic boards with hand-derived expectations, plus no-false-positive tests on clean real boards with their rules. |
| **4** | Engineering intelligence and component context | `services/ai-engine` orchestration (explain finding/component/net/region, design review, recommendations with problem/change/benefit/trade-offs/validation/evidence/confidence). Schema-validated outputs. A verification step that rejects references to objects or numbers not in the context. Tool calls into deterministic calculators. Consent and context limits enforced. `recommendations` table. `component_catalog` and `component_datasheets` with source and verification status (no fabricated specs; empty until filled from a cited source or the user). Evaluation harness with a fake provider. | AI never sees a project without consent. Outputs are labelled "AI suggestion". Invalid or hallucinated references are rejected in tests. |
| **5** | Optimization framework | `services/optimization/` (objectives, constraints, algorithms, candidates, evaluation, comparison). Objectives: area, placement (ratsnest/HPWL), routing efficiency, cost estimate, layer count, thermal, manufacturability. Constraints: locked/fixed, keep-outs, outline, clearances, widths, layers, connectors, user rules. Never silently relaxed. Deterministic algorithms (outline fit, local-search/annealing placement with constraint checks, track-width and via standardization). Pareto front and trade-off presentation. Candidate states: proposed, awaiting validation, validated, rejected, accepted. Optimization jobs on the worker. | Constraint-violation tests. Pareto tests. Candidates never touch the original revision. |
| **6** | Change management, comparison and export | Explicit change sets (move, rotate, track width, via move, outline change; footprint swap only if it can be done safely, otherwise unsupported). Each change has original and proposed values, reason, source, linked findings and validation status. Preview, before/after, undo/rollback, history. New revision created from accepted changes. Export: source-span patching, then KiCad load, KiCad DRC, VIA re-parse and diff check. Unsupported changes are refused with a reason; the original is always preserved. | Round-trip tests on real boards (byte-identical outside the changed objects). Rollback tests. Revision lineage tests. |
| **7** | Viewer and workspace UI | Finding overlays, highlighting components and nets, region selection, layer/component/net filters, finding navigation, before/after and candidate visualization. Web Worker for render-model building and hit-testing. Side panel (findings, explanations, recommendations, selection). Workspace areas: Analysis, Findings, Recommendations, Optimize, Compare, Components, all with loading, empty, error and success states. | Playwright: import → analyse → open finding → board highlights → explain (fake provider in CI) → optimize → compare → accept → export. Large-board responsiveness measured. |
| **8** | Testing, performance and documentation | Load and concurrency tests (concurrent analyses, duplicate jobs, retries, storage and provider failures, rate limits). Performance budgets on the 47 MB board. New docs: `PCB_ANALYSIS.md`, `OPTIMIZATION_ENGINE.md`, `AI_INTELLIGENCE.md`, `FINDINGS_SYSTEM.md`; updates to ARCHITECTURE, API_SPEC, DATABASE, ENGINEERING, ROADMAP. Stage 2 acceptance mapped to tests. | All 14 acceptance criteria verified by named tests or documented limitations. |

Architecture stays a modular monolith. The only new runtime service is the optional
`eda-worker` (decision 1). `services/optimization` becomes a third Python package like
`pcb-engine` and `ai-engine`. No Kubernetes, message brokers or new databases.

## 10. Risks

| Risk | Mitigation |
|---|---|
| KiCad version skew: KiCad 9 DRC on boards made in KiCad 5–8 | Report the KiCad version used. Older boards are upgraded in memory by KiCad, which is normal KiCad behaviour; validated on the 5.1–9.0 demo set |
| False positives erode trust | Rules from the project; clean real boards must produce no VIA errors; every finding carries evidence and its source; confidence below 1 for heuristics |
| AI hallucination | Structured output, reference verification against the design, labels, no AI text presented as a verified result |
| Optimization without routing is limited | Candidates that break routing say so, and validation reflects it; routing-aware optimization is a later stage |
| Export corrupting designs | Patch-in-place, KiCad load and DRC, re-parse diff, original always kept, refuse rather than guess |
| Image size and CI time (KiCad image 2.3 GB) | Separate optional service; CI caches the image; KiCad-dependent tests run in a dedicated job |
| Scope: Stage 2 is large | Strict milestone gates; strongest working foundation over breadth; limitations documented, not hidden |
