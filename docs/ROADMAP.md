# VIA Roadmap

## Stage 1 — Foundation (current)

Each checkpoint is delivered separately, with formatting, linting, type checks
and tests passing before it's marked done.

| CP | Deliverable | Status |
|---|---|---|
| 1 | Repository architecture, implementation plan, **PCB engine core** (S-expr parser, normalized model, geometry, KiCad 5–9 adapter, engineering tests) | ✅ done |
| 2 | Frontend, backend and database running; PCB engine validated on real KiCad 5.1–9.0 boards | ✅ done |
| 3 | Authentication and project management | ✅ done (pending review) |
| 4 | Working PCB upload and parser pipeline | ⏳ next, after CP3 review |
| 5 | PCB viewer, project workspace, AI foundation interfaces | — |
| 6 | Testing hardening, CI, documentation | — |

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

### CP4 — PCB upload and parser pipeline
- `/api/v1/pcb/import`, designs, revisions, files endpoints; size limit, extension + sniff validation, SHA-256 duplicate detection, upload records.
- Worker service (`via_api.worker`, Compose `worker`) + RQ + constrained parser subprocess (`python -I -m via_pcb.cli`, rlimits, timeout, empty env).
- Persist normalized JSON to object storage, extracted rows to `pcb_*` tables, analysis run + activity.
- `/api/v1/pcb/{design_id}`, `/components`, `/nets`, `/layers` (paginated, searchable).
- Web upload UI: drag-and-drop, file picker, client-side validation, progress (XHR), cancellation, metadata display, duplicate and parse error messages.
- Third-party, permissively licensed real KiCad boards added to engineering tests.

### CP5 — PCB viewer, workspace, AI foundation
- SVG viewer from a render model: outline, layer visibility, components, selection, tracks, vias, zones, zoom, pan, fit-to-board, info panel, component search.
- Workspace tabs: Overview, PCB Designs, Files, Components, Analysis (coming soon + import runs), Activity, Settings.
- `services/ai-engine`: provider interfaces (text, structured output, embeddings, model selection), disabled-by-default provider config, project-context interface with authorization and explicit per-operation consent. No AI output in the UI yet.

### CP6 — Testing and documentation
- Playwright e2e: register → create project → upload → view board → select component → logout/login.
- Security regression suite (IDOR, cross-user, invalid uploads, rate limits).
- GitHub Actions: lint, typecheck, unit/integration (Postgres + Redis services), web build, e2e, Docker image build.
- Final PRD, DATABASE, API_SPEC, ENGINEERING, SECURITY, README.

## Later stages (not in Stage 1)
- **VIA Intelligence** — AI review grounded in parsed design data.
- **VIA Optimize** — DRC-style checks, routing/placement suggestions.
- **VIA Learn** — opt-in, privacy-first collective knowledge (consent records already modelled in Stage 1).
- **VIA Studio** — native PCB editor.
- **VIA Connect** — integrations with other EDA tools (more adapters: Altium, Eagle, ODB++, IPC-2581).
