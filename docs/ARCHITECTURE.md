# VIA Architecture (Stage 1 — Foundation)

Status: **Checkpoint 1** — architecture agreed, PCB engine core implemented and tested.
Sections marked *(planned)* describe the design for later checkpoints and will be
updated as they are built.

## 1. System overview

```
             ┌──────────────────────────── browser ─────────────────────────────┐
             │  Next.js app (apps/web) — design system (packages/ui),            │
             │  typed client (packages/api-client), SVG PCB viewer               │
             └───────────────┬──────────────────────────────────────────────────┘
                             │ same-origin /api/* (Next.js rewrite → API)
                             │ httpOnly session cookie
┌────────────────────────────▼───────────────────────────────┐
│ FastAPI (apps/api)  /api/v1/...                             │
│  auth · users · organizations · projects · designs ·        │
│  revisions · files · pcb · activity                         │
│  authorization, validation, rate limiting, audit log        │
└──────┬──────────────────┬─────────────────────┬─────────────┘
       │ SQLAlchemy       │ enqueue job (RQ)    │ put/get objects (presigned/internal)
┌──────▼─────┐     ┌──────▼─────┐        ┌──────▼────────────────┐
│ PostgreSQL │     │   Redis    │        │ S3-compatible storage │
│ (Alembic)  │     │ queue+rate │        │ (MinIO in dev)        │
└──────▲─────┘     └──────┬─────┘        └──────▲────────────────┘
       │                  │ dequeue            │
┌──────┴──────────────────▼────────────────────┴──────────────┐
│ Worker (apps/api, `via-worker`)                              │
│  fetch file → spawn constrained parser subprocess →          │
│  persist normalized design + extracted rows                  │
│      ┌─────────────────────────────────────────────┐         │
│      │ parser subprocess: python -I -m via_pcb.cli │         │
│      │ stdin=bytes, stdout=JSON, rlimits, timeout, │         │
│      │ empty env, no DB/storage credentials        │         │
│      └─────────────────────────────────────────────┘         │
└──────────────────────────────────────────────────────────────┘
```

One API service, one worker, one web app. No microservices: the worker is the
same Python codebase started with a different entry point.

## 2. Repository layout

```
via/
  apps/
    web/                Next.js (App Router) application            (planned, CP2)
    api/                FastAPI app + worker, Alembic migrations    (planned, CP2)
  packages/
    ui/                 shared design-system components (shadcn-style)  (planned, CP3)
    types/              TypeScript types for API + normalized PCB model (planned, CP2)
    api-client/         typed fetch client used by apps/web            (planned, CP2)
  services/
    pcb-engine/         ✅ implemented
      src/via_pcb/
        parser/         S-expression syntax parser (format-level, no semantics)
        models/         normalized PCB model (Pydantic) — the internal contract
        geometry/       pure geometry helpers (rotation, arcs, outline assembly)
        adapters/       format adapters + registry (KiCad today)
    ai-engine/          provider abstraction + project context  (planned, CP5)
      src/via_ai/{providers,prompts,schemas,context}
  infrastructure/
    docker/             Dockerfiles                               (planned, CP2)
    database/           Postgres init (test database, extensions)  (planned, CP2)
    storage/            bucket bootstrap for MinIO                 (planned, CP2)
  tests/
    unit/               fast, isolated tests (engine, API units)
    engineering/        ✅ parser verified against known source designs
    integration/        API + DB + storage tests                   (planned, CP3)
    e2e/                Playwright                                 (planned, CP6)
  docs/                 PRD, ARCHITECTURE, DATABASE, API_SPEC, ENGINEERING, SECURITY, ROADMAP
  scripts/              developer scripts                          (planned, CP2)
```

### Deviations from the brief's layout (and why)

| Brief | Actual | Reason |
|---|---|---|
| `services/pcb-engine/{parser,models,geometry,adapters}` | `services/pcb-engine/src/via_pcb/{...}` | Python needs an importable package; a top-level `parser` module would shadow other packages. `src/` layout prevents accidentally importing the uninstalled tree in tests. |
| `services/ai-engine/{providers,prompts,schemas}` | `services/ai-engine/src/via_ai/{providers,prompts,schemas,context}` | Same reason; `context/` added for the project-context interface required by the AI foundation. |
| Worker not listed | Worker lives in `apps/api` (`via_api.worker`) | It shares models, settings and storage code with the API; a separate app would duplicate them. |
| Vitest tests under `tests/` | Colocated `*.test.ts` in each TS package | Vitest/TS path resolution is simplest per package. Python and Playwright tests stay in `tests/`. |
| Empty module directories | Created only when they get code | Per the brief: no empty modules. |

## 3. Key decisions

| Decision | Choice | Alternatives considered |
|---|---|---|
| Monorepo tooling | pnpm workspaces (TS) + uv (Python); no Turborepo/Nx yet | Turborepo — unnecessary for one app. |
| Normalized PCB model | Pydantic v2 models in `via_pcb.models`, mm units, absolute coordinates, semver `SCHEMA_VERSION` | Protobuf/JSON Schema first — more ceremony; we export JSON Schema from Pydantic when needed. |
| Format support | Adapter registry (`PCBAdapter`): sniff + parse → `PCBDesign` | Using KiCad's own Python API (`pcbnew`) — needs a full KiCad install and executes native code against untrusted input. A pure-Python parser is portable and safer. |
| Parsed data persistence | Full normalized JSON in object storage (one per revision) **plus** queryable rows (`pcb_components`, `pcb_nets`, `pcb_layers`, `pcb_geometry` summary) | Every track/pad as a row — huge tables for no Stage 1 query need. JSON-only — no pagination/search for components & nets. |
| Background parsing | RQ (Redis) worker, parser in a **subprocess** with rlimits + timeout + empty env | FastAPI `BackgroundTasks` — runs in the API process (violates isolation). Celery — heavier. A separate no-network parser container — stronger, but premature; documented as future hardening. |
| Authentication | Server-side sessions: random 256-bit token in an httpOnly cookie, SHA-256 hash stored in `user_sessions`; Argon2id passwords | JWT — cannot be revoked without a denylist; logout/session management are requirements. |
| Web ↔ API | Next.js rewrites `/api/*` to the API, so the browser is same-origin; API also accepts `Authorization: Bearer <session token>` for programmatic clients | Cross-origin cookies + CORS — more CSRF/CORS surface. |
| CSRF | SameSite=Lax cookie + required `X-VIA-Request: 1` header on unsafe methods for cookie-authenticated requests | Double-submit tokens — unnecessary given same-origin + custom header. |
| PCB viewer | SVG, rendered from a viewer-specific *render model* derived from the API's normalized JSON (`apps/web/lib/pcb/render-model.ts`) | Canvas/WebGL — better for very large boards; the render-model boundary lets us swap renderers later without touching the data model. |
| Object storage | `StorageBackend` interface with S3 (boto3; MinIO in dev) and local-filesystem implementations | Storing files in Postgres — explicitly disallowed. |
| Authorization | Central `authorize(user, project, action)` in the API service layer; roles `owner/editor/viewer`; projects private by default | Postgres RLS — valuable later, adds complexity now. |

## 4. Data model *(planned, CP2 — details in DATABASE.md once implemented)*

All tables: UUID primary keys, `created_at`/`updated_at` as `timestamptz` in UTC.

- **users**, **user_sessions** (hashed token, expiry, ip, user agent), **password_reset_tokens** (hashed, single-use, expiring)
- **organizations**, **organization_memberships** (role) — every user gets a personal organization; projects belong to an organization and have an owner user.
- **projects** (`visibility='private'` default, `archived_at`, `learn_contribution_enabled=false`), **project_memberships** (role)
- **designs** → **design_revisions** (revision number, status `pending|processing|ready|failed`, parser version, warnings, object counts, imported_at)
- **design_files** (kind `source|normalized`, storage key, sha256, size, content type)
- **upload_records** — every upload attempt including rejected ones (sha256, size, outcome, reason); duplicate detection by `(project_id, sha256)`
- **pcb_layers**, **pcb_nets**, **pcb_components**, **pcb_geometry** (outline, bbox, area, storage key of full geometry)
- **analysis_runs** — Stage 1 records `pcb_import` runs (status, timings, error); later stages add analysis kinds
- **activity_logs** — user-visible activity and security audit events (actor, action, target, ip, metadata)
- **data_consents** — explicit, revocable consent records for future VIA Learn contribution (none granted by default)

## 5. Request flow: PCB import *(planned, CP4)*

1. `POST /api/v1/pcb/import` (multipart) → auth + `editor` permission on project → rate limit.
2. Stream to a temp file while hashing and enforcing `MAX_UPLOAD_BYTES`; check extension + sniff header via the adapter registry (no parsing in the API).
3. Duplicate check on `(project_id, sha256)` → `409` with the existing revision.
4. Put object at a server-generated key `projects/{project_id}/revisions/{revision_id}/source` (never a user-supplied path).
5. Create design/revision (`pending`), upload record, analysis run, activity entry; enqueue job → `202 Accepted`.
6. Worker: download → run parser subprocess → on success write normalized JSON object and extracted rows, mark `ready`; on failure store a safe error message and mark `failed`.
7. Web polls the revision status and then loads `/api/v1/pcb/{design_id}` and paginated components/nets/layers.

## 6. Technical risks

| # | Risk | Impact | Mitigation |
|---|---|---|---|
| 1 | **KiCad format drift** (KiCad 9 renumbered layers; KiCad 10 is expected to drop the board net table) | Wrong/missing data | Name-based layer handling (never index-based); net names resolved from pads when no net table; version warnings outside the tested range; per-version fixtures. |
| 2 | **Legally usable real-world fixtures** | Brief requires real sample projects | Hand-authored fixtures (original work) cover exact-value checks today. Third-party boards must have a permissive licence (CC0, CC-BY, CERN-OHL-P, MIT); provenance + licence recorded in `tests/engineering/fixtures/README.md`. Needs a decision from the project owner on GPL-licensed KiCad demo boards. |
| 3 | **Large boards** (50k+ primitives; multi-MB JSON) | Slow viewer, slow API | Gzip responses; per-section endpoints; SVG grouped per layer; render-model boundary allows a Canvas/WebGL renderer later. |
| 4 | **Untrusted file parsing** (zip bombs don't apply, but pathological nesting/size do) | DoS of API/worker | Size limit before storage; parser in subprocess with CPU/memory/time limits; iterative (non-recursive) parser; warning caps. |
| 5 | **Pad/graphic transform semantics** (pad angle stored as absolute; bottom-side local coordinates pre-mirrored) | Misplaced pads in viewer | Verified with hand-computed rotated fixtures; must be confirmed against real KiCad-exported boards in CP4. |
| 6 | **No Docker daemon in the current dev container** | `docker compose up` can't be executed here | Services verified natively (Postgres 16 and Redis are installed); images built and smoke-tested in GitHub Actions. |
| 7 | **Bleeding-edge frontend stack** (Next 16, React 19, Tailwind 4) | Integration friction | Exact pins; shadcn components vendored into `packages/ui` rather than generated at install time. |
| 8 | **Scope creep** | Stage 1 never finishes | Coming-soon states for non-Stage-1 sections; no fabricated data or AI output. |
