# VIA Roadmap

## Stage 1 — Foundation (current)

Each checkpoint is delivered separately, with formatting, linting, type checks
and tests passing before it's marked done.

| CP | Deliverable | Status |
|---|---|---|
| 1 | Repository architecture, implementation plan, **PCB engine core** (S-expr parser, normalized model, geometry, KiCad 5–9 adapter, engineering tests) | ✅ done |
| 2 | Frontend, backend and database running; PCB engine validated on real KiCad 5.1–9.0 boards | ✅ done |
| 3 | Authentication and project management | ✅ done |
| 4 | Working PCB upload and parser pipeline | ✅ done |
| 5 | PCB viewer, AI foundation interfaces | ✅ done |
| 6 | Testing hardening, CI, documentation | ✅ done (pending review) |

### CP2 — Frontend, backend and database running ✅
- `apps/api`: FastAPI app factory, settings (pydantic-settings) with production safety checks, request IDs, security headers, strict CORS, consistent error envelope, `/api/v1/health` + `/api/v1/health/ready` (DB with migration state, Redis, storage), OpenAPI.
- SQLAlchemy models for **all** Stage 1 entities (18 tables) + initial Alembic migration; round trip and model-parity tests on real Postgres.
- Storage abstraction (S3/MinIO + local filesystem) with server-generated, validated keys.
- `apps/web`: Next.js App Router, Tailwind 4, dark-first tokens with light theme, accessible primitives, live system status page; `/api/*` same-origin rewrite; CSP.
- `packages/types`, `packages/api-client` (typed client, error envelope, CSRF header), `packages/ui`.
- `docker-compose.yml`: postgres, redis, minio (built from pinned official source), migrate job, api, web. Dockerfiles in `infrastructure/docker`.
- PCB engine: real-board validation (KiCad 5.1–9.0), pad-angle investigation, two bugs fixed.
- GitHub Actions CI. *Changed from plan:* the worker service moved to CP4 (no jobs exist yet); `scripts/dev.sh` replaced by README instructions (Compose infra + native API/web).

### CP3 — Authentication and project management ✅
- Register, login, logout, `/auth/me`, session listing/revocation, password reset (hashed single-use tokens; dev logs the email), profile and password change.
- Argon2id, server-side sessions (cookie or Bearer), CSRF header enforcement, Redis rate limiting, audit events.
- Personal organization on registration; organizations: list, read, create team org, list members.
- Projects: create, rename, describe, visibility, archive/unarchive, delete, search/filter/sort/paginate, members (add by email, role change, remove, leave). Central authorization service; org and project permissions independent.
- Activity feed (`/api/v1/activity`).
- Web: design system additions (inputs, field, select, dialog, tooltip, dropdown menu, table), auth pages, protected app shell, dashboard (real data), projects list, project workspace, activity, account settings.
- Tests: auth, projects, security isolation suite (pytest); auth flows, session guard, project creation, projects table, workspace roles (Vitest); end-to-end walkthrough in a real browser.
- *Changed from plan:* the full project workspace (Overview, PCB Designs, Files, Components, Analysis, Activity, Settings) was built now, with honest coming-soon panels for the sections that depend on CP4/CP5. Organization invitations are out of Stage 1 scope.

### CP4 — PCB upload and parser pipeline ✅
- `POST /api/v1/pcb/import` with Content-Length guard, streaming size + SHA-256, extension/sniff validation, per-project duplicate detection, upload records; designs, revisions (polling), files (list + download), board summary, normalized JSON, components/nets/layers (paginated, searchable). Design/project deletion removes stored objects.
- RQ worker (`via-api worker`, Compose `worker`) with a failure callback; parser in a credential-free, rlimited subprocess; results validated, persisted as gzipped JSON in storage plus queryable rows; analysis runs and activity.
- Migration `0002` (`design_revisions.summary`).
- Web: drag-and-drop/file-picker upload with progress, cancel, live parse status, duplicate and failure messages; design page (board info, source, warnings, components, nets, layers, revisions); Files and Components tabs; dashboard upload shortcut.
- Verified with the real KiCad 8 `video` board end to end and a 47 MB stress board. Findings fixed: Next.js truncated proxied bodies at 10 MB; parser memory default raised to 3 GiB (~35× input).
- *Not done:* committing permissively licensed real boards (CC0/CC-BY/MIT/CERN-OHL-P). Not attempted in CP4; validation still uses the CC BY-SA KiCad demos, fetched on demand.

### CP5 — PCB viewer, AI foundation ✅
- Board viewer (Canvas 2D) from the normalized design through a separate render model: outline, layer visibility (grouped, colour-coded, sensible defaults), components, selection (click or search), tracks, vias, drills, zone outlines, zoom (wheel, buttons, keys), pan (drag, arrows), fit, info panel with properties and pad nets, accessible canvas description. Embedded on the design page plus a full-page route. Large boards use snapshot previews while interacting.
- `services/ai-engine`: provider interface (text, structured output, embeddings, capabilities), model routing per task, disabled default, Anthropic adapter (optional extra), `ProjectContext` schema. API: `/ai/status`, per-project external-AI consent, consent-gated `DatabaseContextProvider`.
- *Changed from plan:* no `prompts/` module yet (no prompts exist until the first AI feature); the project workspace already shipped in CP3/CP4.

### CP6 — Testing and documentation ✅
- Playwright end-to-end suite (`apps/web/e2e`) against the full Compose stack: register → create project → edit details → upload → components, nets, layers → viewer → search and select a component → sign out → redirect → sign in → project still there; private-project isolation between two real users (UI and every read endpoint); invalid, spoofed, duplicate and unparseable uploads; signed-out redirect with return.
- Route-wide security regression suite (`tests/integration/test_security_regression.py`): walks every API route, so new endpoints are covered automatically: authentication required (401), CSRF header required on every unsafe route, 404 for every project/design/revision/file/organization/session-scoped route to a user without access (and nothing changed), each rate limit enforced on its real endpoint, account lockout, client address never taken from request headers, upload filename sanitization.
- GitHub Actions: the Docker job now builds the images, starts the whole stack (waits for `/api/v1/health/ready` through the web app) and runs the Playwright suite against it; logs and the Playwright report are uploaded on failure.
- Docs: PRD acceptance criteria mapped to the tests that verify them; README, ARCHITECTURE, SECURITY, API_SPEC updated.
- *Found:* `X-Forwarded-For` sent by a browser passes through Next.js unchanged (Next only sets it when absent), so with the API trusting the web container a client could choose the IP used for per-IP rate limits. Safe only behind a reverse proxy that overwrites the header; documented as a deployment requirement in SECURITY.md and README. Per-account and per-user limits are unaffected.

## Stage 2: PCB Intelligence & Optimization (current)

Audit and plan: [STAGE_2_AUDIT.md](STAGE_2_AUDIT.md). Each milestone is a checkpoint approved by the project owner.

Decisions (owner, 2026-11-26):
- KiCad 9 (official image, GPL-3, separate optional service) is approved for DRC and validation.
- Export patches the original file in place.
- Projects are imported as `.zip`.
- No named manufacturer profiles: VIA defaults plus user-defined profiles.
- No AI key: the provider stays disabled, and tests use a fake provider.
- Optimization scope as proposed in the audit (§8.6), pending explicit confirmation.

| M | Deliverable | Status |
|---|---|---|
| 1 | Audit fixes and PCB model 1.1 | ✅ done |
| 2 | Findings and analysis framework | ✅ done |
| 3 | Deterministic analysis and KiCad DRC | ✅ done |
| 4 | Engineering intelligence and component context | ✅ done |
| 5 | Optimization framework | ✅ done |
| 6 | Change management, comparison and export | ✅ done |
| 7 | Viewer and workspace UI | ✅ done |
| 8 | Testing, performance and documentation | ✅ done |

### M8: Testing, performance and documentation ✅
- **Concurrency** (`tests/integration/test_concurrency.py`, real threads with separate connections). Each test fails without its fix:
  - identical concurrent analysis starts share one run;
  - one apply per design at a time;
  - concurrent applies of one change set run once;
  - revision numbers never collide (concurrent uploads could crash before);
  - an export whose base stopped being current is refused.
- **Failure modes** (`tests/integration/test_failure_modes.py`):
  - storage outages during upload, analysis and export, and the export can be retried afterwards;
  - AI provider outage and refusal give 503/422 and store nothing.
- **Performance** (ENGINEERING.md "Stage 2 performance"):
  - exporting the 50 MB stress board went from 83 s and 4.7 GB (failed in the sandbox) to 54 s within the 3 GB sandbox limit;
  - export of the 8.5 MB board: 8.4 s → 3.5 s;
  - load test against the Compose stack: no errors, API p95 81 ms while analyses run.
- **Fixes found on the way:**
  - AI grounding treated numbers inside UUIDs as design data;
  - the project Analysis tab still showed a "coming soon" panel;
  - Compose tried to pull the locally built API image;
  - CI's stale apt index broke the Chromium install.
- **Docs:** STAGE_2_ACCEPTANCE.md maps the 14 acceptance criteria to tests and limits; performance and load results added to ENGINEERING.md.

### M7: Viewer and workspace UI ✅
- **Viewer:**
  - finding overlays (severity-coloured regions, highlighted components and net copper) that zoom to the selection;
  - boards load, parse and build their render model in a Web Worker.
- **Design workspace tabs:**
  - **Analysis:** run or re-run; run summary with per-check status; findings filtered by severity, source, category and status, with search; a finding panel with source, verification, confidence, measured evidence, suggested resolution, review (reason required to dismiss) and history; AI explain and AI design review with recommendations, shown only when a provider is configured and always labelled "AI suggestion · unverified" with VIA's grounding result.
  - **Optimize:** objectives, candidates with validation state, Pareto badge, metric before/after/delta, benefits, trade-offs and changes; accept (validated only) or reject (reason required); create a change set from accepted candidates.
  - **Changes:** change sets with status, changes, simulated preview, undo and discard, apply, download, rollback, and the revision comparison (findings resolved or introduced).
  - **Revisions:** lineage ("from rev N by a change set") and the current marker.
- **Client:** typed `ai`, `optimization` and `changes` methods in `@via/api-client`, and their types in `@via/types`.
- **Tests:**
  - unit tests for overlays, labels and the panels;
  - a Playwright flow against the real stack: analyse, inspect a finding, optimize, accept, change set, apply, compare, download, roll back.

### M6: Change management, comparison and export ✅
- **Export:**
  - `via_pcb.patch` edits the original KiCad file in place by stable id, for move, rotate, track width, via move and size, and outline rectangle;
  - `via_opt.export` verifies the result by re-parsing and comparing with `apply()`;
  - project archives keep every other member untouched;
  - byte-identical round trips on KiCad 5 to 9 boards.
- **Data:** migration `0008` (`change_sets`, change status and origin, revision lineage, `pcb_export` runs).
- **API:**
  - change sets from accepted candidates or user changes, with conflict detection;
  - simulated preview, undo and discard;
  - apply as a background job in the sandbox, producing a new child revision;
  - automatic follow-up analysis;
  - revision comparison by finding fingerprint;
  - download, rollback, history and lineage.
- **Docs:** new CHANGE_MANAGEMENT.md.

### M5: Optimization framework ✅
- **`services/optimization` (`via_opt`):**
  - an explicit change model with `apply` (never mutates the original);
  - seven objectives with deterministic metrics, including an illustrative relative cost index;
  - constraints (fixed/locked parts, connectors, keep-outs, outline, margins, size limits);
  - generators: outline fit, via standardization, track widening (profile and IPC-2221), greedy ratsnest placement, layer-reduction proposal;
  - validation by re-running VIA's checks on the modified design (`requires_rerouting` and `manual` states are honest);
  - a Pareto front.
- **Data:** migration `0007` (`optimization_candidates`, `design_changes`, `pcb_optimization` runs).
- **API:** runs, candidates, comparison and decisions (only validated candidates can be accepted). Runs share the worker lifecycle.
- **Docs:** new OPTIMIZATION_ENGINE.md.

### M4: Engineering intelligence and component context ✅
- **`via_ai`:**
  - versioned prompts;
  - strict output schemas (explanation, design review with findings separated from hypotheses, recommendations with benefits, trade-offs, validation, evidence and confidence);
  - orchestration and a grounding verification step that rejects invented objects or numbers;
  - a scripted provider and an evaluation harness.
- **Context:** now includes analysis findings with evidence, the focused object (finding, component, net or region), project rules and matched component records.
- **API:**
  - explain (design or finding) and design review;
  - recommendations with decisions;
  - an `ai_outputs` audit trail, accepted and rejected;
  - component records with sourced specs, and part-number matching from footprint properties (migration `0006`);
  - consent, rate limit (30/h) and the security suite cover all routes.
- **Docs:** new AI_INTELLIGENCE.md.
- **AI remains disabled by default; no key is configured.**

### M3: Deterministic analysis and KiCad DRC ✅
- **KiCad DRC:** the `eda` service (KiCad 9.0.6 official image, no credentials, internal network, hardened) and the `kicad_drc` check:
  - violations mapped to objects by UUID or description;
  - default-rules results marked heuristic;
  - environment-only library checks suppressed.
- **Geometry kernel:** exact core+radius copper shapes, spatial grid.
- **Checks:**
  - connectivity: islands, single-pad nets, layer usage;
  - manufacturing against profiles: width, vias, pad holes, hole spacing, copper-to-edge, copper spacing, silkscreen;
  - placement: orientation, connector edge access, decoupling, board space;
  - routing: detours, net-class widths;
  - IPC-2221 current capacity and IPC-2141 microstrip impedance, run only with user inputs.
- **Profiles:** VIA conservative/advanced plus project profiles (migration `0005`, CRUD API); start options; exact profile values snapshotted per run.
- **Validation:** no spacing or island findings on real KiCad 6–9 boards where KiCad's DRC with project rules reports none; e2e test with real KiCad DRC in CI.
- **Fixed (real bugs found by the new checks):**
  - KiCad 5 default via drills had been recorded as 0 (750 of 815 vias in the 5.1 `video` demo).
  - ENGINEERING.md wrongly said KiCad's DRC refills zones (KiCad 9.0.6's CLI doesn't).
- *Tests changed because behaviour changed:* framework tests pin their original checks; the "no warnings on real boards" test allows the new informational `via_default_drill` note.

### M2: Findings and analysis framework ✅
- **Engine (`via_pcb.analysis`):**
  - the unified `Finding` (category, severity, source, verification, confidence, object references by stable id, components, nets, region, evidence, resolution, cross-revision fingerprint);
  - the `Check` contract with skip reasons and versions;
  - a registry;
  - an engine that isolates failing checks and rejects findings attributed to the wrong check or source.
- **Starter checks (exact):** board outline (missing, or open with unjoined endpoints marked), project rules availability, import warnings, copper pads without a net. Deliberately simple; Milestone 3 adds KiCad DRC and the real deterministic checks.
- **Persistence (migration `0004`):**
  - findings, evidence and append-only review history;
  - run provenance: config, per-check outcome and version, analysis/parser/schema versions;
  - immutable run history.
- **Worker:** `analyze_run` with the same heartbeat and reaper recovery as imports; designs parsed before schema 1.1 are re-imported first.
- **API:**
  - checks catalog;
  - start (idempotent, rate limited), run history and status;
  - findings filter/sort/search with facets, and detail with evidence and history;
  - review, dismiss (reason required) and reopen;
  - compare two runs (new / resolved / persisting).
  - Review decisions carry over to the same issue in later revisions.
- **Security:** the route-wide suite now covers `run_id`/`finding_id`, a compare query parameter and the analysis rate limit.
- **Clients:** typed API client methods and types.
- **Docs:** new FINDINGS_SYSTEM.md and PCB_ANALYSIS.md.
- *Changed from plan:* the analysis UI stays in Milestone 7 as planned; this milestone is engine, persistence and API (verified end to end with the real worker on the KiCad 9 `video` project).

### M1: Audit fixes and PCB model 1.1 ✅
- **Job recovery (audit D1, a real Stage 1 bug):**
  - heartbeats on running imports;
  - a reaper in the worker's maintenance loop that re-queues stale or lost work as a new attempt, up to 3 attempts, then fails it with `worker_lost`;
  - RQ abandoned-job reports handled the same way, with superseded callbacks ignored;
  - migration `0003`;
  - tested by SIGKILLing a real worker process tree mid-parse.
  - It also recovered (failed visibly) the revision stranded during the audit.
- **PCB model 1.1.0 (additive):**
  - stable `id` and source `uuid` on components, pads, tracks, vias and zones;
  - `locked` on footprints, tracks and vias;
  - stackup;
  - keep-out rules;
  - zone priority, clearance and minimum thickness;
  - pad margins, roundrect ratio and zone connection.
  - Verified on a new hand-authored KiCad 9 fixture and against independent counts on the ten real boards.
- **KiCad project `.zip` import:**
  - safe archive handling;
  - `.kicad_pro` rules and net classes (KiCad 6 lists, 7+ patterns, 8 assignments);
  - `.kicad_dru` custom rules (recorded, not evaluated);
  - `constraints.rules_source`.
  - Real KiCad 6–9 projects are pinned in the fixture manifest.
  - Web: the upload accepts `.zip`, and the design page shows where its rules came from.
- *Tests changed because behaviour changed:* two tests used `.zip` as their example of an unsupported format, and now use Altium `.PcbDoc`; hard-coded engine and schema versions now come from the constants.

## Later stages
- **VIA Intelligence** — AI review grounded in parsed design data.
- **VIA Optimize** — DRC-style checks, routing/placement suggestions.
- **VIA Learn** — opt-in, privacy-first collective knowledge (consent records already modelled in Stage 1).
- **VIA Studio** — native PCB editor.
- **VIA Connect** — integrations with other EDA tools (more adapters: Altium, Eagle, ODB++, IPC-2581).
