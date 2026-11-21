# VIA Roadmap

## Stage 1 — Foundation (current)

Each checkpoint is delivered separately, with formatting, linting, type checks
and tests passing before it's marked done.

| CP | Deliverable | Status |
|---|---|---|
| 1 | Repository architecture, implementation plan, **PCB engine core** (S-expr parser, normalized model, geometry, KiCad 5–9 adapter, engineering tests) | ✅ done |
| 2 | Frontend, backend and database running | ⏳ next |
| 3 | Authentication and project management | — |
| 4 | Working PCB upload and parser pipeline | — |
| 5 | PCB viewer, project workspace, AI foundation interfaces | — |
| 6 | Testing hardening, CI, documentation | — |

### CP2 — Frontend, backend and database running
- `apps/api`: FastAPI app factory, settings (pydantic-settings), structured logging, consistent error envelope, `/api/v1/health` (DB + Redis + storage checks), OpenAPI.
- SQLAlchemy models for **all** Stage 1 entities + initial Alembic migration; `alembic upgrade head` / `downgrade base` tested against Postgres.
- Storage abstraction (S3/MinIO + local filesystem).
- `apps/web`: Next.js App Router, Tailwind 4, dark-first theme tokens, app shell; `/api/*` rewrite to the API.
- `packages/types`, `packages/api-client` (health only at this stage).
- `docker-compose.yml`: postgres, redis, minio (+ bucket bootstrap), api (runs migrations), worker, web. Dockerfiles in `infrastructure/docker`.
- `.env.example` complete; `scripts/dev.sh` for running natively without Docker.
- **Exit:** compose config validates; API, web and DB run natively; migration round-trip test passes.

### CP3 — Authentication and project management
- Register, login, logout, `GET /auth/me`, session listing/revocation, password-reset request/confirm (token foundation; email delivery logs in dev).
- Argon2id hashing, session cookies, CSRF header check, Redis rate limiting on auth.
- Personal organization on registration; organizations + memberships endpoints (read/list, minimal create).
- Projects: create, rename, edit description, archive/unarchive, delete, search/filter, pagination; owner + project memberships; private by default.
- Activity log + audit events; `/api/v1/activity`.
- Web: design system (buttons, inputs, cards, dialogs, tables, navigation, tooltips, badges, empty/loading/error states), auth pages, protected routes, dashboard (real data only), project list + details.
- **Exit:** pytest integration tests for auth, projects, ownership, cross-user isolation; Vitest for client + forms.

### CP4 — PCB upload and parser pipeline
- `/api/v1/pcb/import`, designs, revisions, files endpoints; size limit, extension + sniff validation, SHA-256 duplicate detection, upload records.
- RQ worker + constrained parser subprocess (`python -I -m via_pcb.cli`, rlimits, timeout, empty env).
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
