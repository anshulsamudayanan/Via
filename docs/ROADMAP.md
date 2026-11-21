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
| 5 | PCB viewer, AI foundation interfaces | ✅ done (pending review) |
| 6 | Testing hardening, CI, documentation | ⏳ next, after CP5 review |

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
