# VIA Architecture (Stage 1 — Foundation)

Status: **Checkpoint 6, Stage 1 complete**. Accounts, projects and sharing; the PCB pipeline
(upload, validation, sandboxed parsing, persistence); an interactive board viewer; the AI
foundation (interfaces, disabled by default, consent-gated context); unit, integration,
route-wide security and end-to-end browser tests in CI.
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
    api/                          ✅ FastAPI app (CP2 foundation)
      src/via_api/
        config.py                 settings from VIA_* env vars, production safety checks
        db.py                     engine, sessions, alembic_config()
        errors.py middleware.py   error envelope; request id, security headers
        models/                   SQLAlchemy models for all Stage 1 entities
        migrations/               Alembic env + versions (bundled in the package)
        storage/                  StorageBackend: S3-compatible (MinIO) and local
        security.py ratelimit.py  Argon2id + token hashing; Redis fixed-window limits
        deps.py                   current user (cookie/Bearer), client info, limiter, mailer
        services/                 business logic: auth, access (authorization), projects, activity
        schemas/                  request/response models
        routes/                   health, auth, users, organizations, projects, activity, pcb, designs, files
        parsing/                  sandbox.py (constrained parser subprocess), importer.py (persist results)
        jobs.py                   RQ queue + job entry points + failure callback
        cli.py                    via-api migrate | init-storage | serve | check
      requirements.lock           locked third-party deps for the Docker image
    web/                          ✅ Next.js (App Router)
      app/(public)/               landing, system status
      app/(auth)/                 login, register, forgot/reset password
      app/(app)/                  protected: dashboard, projects, project workspace, activity, settings
      components/ lib/ test/      UI composition, client helpers, Vitest helpers
      lib/pcb/                    viewer: render model, viewport math, Canvas renderer, palette
      components/viewer/          BoardViewer (canvas, layers, components, info panel)
      proxy.ts                    signed-out page-load redirect (UX only; API is the boundary)
  packages/
    ui/                           ✅ design tokens + accessible primitives (grows in CP3)
    types/                        ✅ TS mirror of API schemas
    api-client/                   ✅ typed fetch client (error envelope, CSRF header)
  services/
    pcb-engine/                   ✅ parser, normalized model, geometry, KiCad adapter
      src/via_pcb/{parser,models,geometry,adapters}
    ai-engine/                    ✅ provider interface, routing, context schema (no AI features yet)
      src/via_ai/{providers/, routing.py, context.py}
  infrastructure/
    docker/                       ✅ api, web, minio Dockerfiles
    database/                     ✅ Postgres init (creates the integration-test database)
  tests/
    unit/                         ✅ engine + API units
    engineering/                  ✅ hand-computed fixtures + real KiCad 5.1-9.0 boards
    integration/                  ✅ real Postgres, Redis, MinIO
  scripts/                        ✅ fetch_real_fixtures.py
  docs/                           PRD, ARCHITECTURE, DATABASE, API_SPEC, ENGINEERING, SECURITY, ROADMAP
  docker-compose.yml  .env.example  .github/workflows/ci.yml
```

### Deviations from the brief's layout (and why)

| Brief | Actual | Reason |
|---|---|---|
| `services/pcb-engine/{parser,models,geometry,adapters}` | `services/pcb-engine/src/via_pcb/{...}` | Python needs an importable package; a top-level `parser` module would shadow other packages. `src/` layout prevents accidentally importing the uninstalled tree in tests. |
| `services/ai-engine/{providers,prompts,schemas}` | `services/ai-engine/src/via_ai/{providers/, routing.py, context.py}` | Importable package (same reason as the PCB engine). Schemas live with their modules; `routing.py` is model selection; `context.py` is the project-context contract. No `prompts/` until a feature has prompts (no empty modules). |
| Worker not listed | Worker will live in `apps/api` (`via_api.worker`, CP4) | It shares models, settings and storage code with the API; a separate app would duplicate them. Not created in CP2: it would be an empty module until jobs exist. |
| `infrastructure/storage/` | Not created | Bucket bootstrap is `via-api init-storage` (dev only, guarded by `VIA_S3_AUTO_CREATE_BUCKET`), run by the Compose `migrate` job. |
| `apps/api/alembic/` | `apps/api/src/via_api/migrations/` | Migrations ship inside the package, so a normal (non-editable) install in Docker finds them. `apps/api/alembic.ini` remains for the `alembic` CLI. |
| Vitest tests under `tests/` | Colocated `*.test.ts` in each TS package | Vitest/TS path resolution is simplest per package. Python tests stay in `tests/`. |
| Playwright tests in `tests/e2e/` | `apps/web/e2e/` (`*.spec.ts`), run against the Compose stack | Uses the web app's pnpm dependencies and strict tsconfig (typechecked and linted with it); no separate JS package. |
| Empty module directories | Created only when they get code | Per the brief: no empty modules. |

## 3. Key decisions

| Decision | Choice | Alternatives considered |
|---|---|---|
| Monorepo tooling | pnpm workspaces (TS) + uv (Python); no Turborepo/Nx yet | Turborepo — unnecessary for one app. |
| Normalized PCB model | Pydantic v2 models in `via_pcb.models`, mm units, absolute coordinates, semver `SCHEMA_VERSION` | Protobuf/JSON Schema first — more ceremony; we export JSON Schema from Pydantic when needed. |
| Format support | Adapter registry (`PCBAdapter`): sniff + parse → `PCBDesign` | Using KiCad's own Python API (`pcbnew`) — needs a full KiCad install and executes native code against untrusted input. A pure-Python parser is portable and safer. |
| Parsed data persistence | Full normalized JSON in object storage (one per revision) **plus** queryable rows (`pcb_components`, `pcb_nets`, `pcb_layers`, `pcb_geometry` summary) | Every track/pad as a row — huge tables for no Stage 1 query need. JSON-only — no pagination/search for components & nets. |
| Background parsing | RQ 2.12 (Redis) worker, fork per job; parser in a **subprocess** with rlimits + timeout + empty env | FastAPI `BackgroundTasks` — runs in the API process (violates isolation). Celery — heavier. RQ 3.0 — new major, not yet needed. A separate no-network parser container — stronger, but premature; documented as future hardening. |
| Parsed data in storage | Normalized `PCBDesign` stored gzipped (`normalized.json.gz`), served with `Content-Encoding: gzip` without re-encoding | Storing the JSON in Postgres JSONB: multi-MB rows for data that's only read whole. |
| Uploads through the web proxy | Browser → Next.js rewrite → API, with `experimental.proxyClientMaxBodySize` set from `VIA_MAX_UPLOAD_BYTES` (Next buffers and truncates proxied bodies at 10 MB by default; found with a 47 MB stress board) | Presigned direct-to-S3 uploads: better for large files and for Vercel, more moving parts. Planned if upload sizes or hosting require it. |
| Authentication | Server-side sessions: random 256-bit token in an httpOnly cookie, SHA-256 hash stored in `user_sessions`; Argon2id passwords | JWT — cannot be revoked without a denylist; logout/session management are requirements. |
| Web ↔ API | Next.js rewrites `/api/*` to the API, so the browser is same-origin; API also accepts `Authorization: Bearer <session token>` for programmatic clients | Cross-origin cookies + CORS — more CSRF/CORS surface. |
| Route protection (web) | Client `SessionProvider` asks the API (`/auth/me`) and redirects on 401; `proxy.ts` additionally redirects signed-out *page loads* (detected via `Sec-Fetch-Dest: document`) | Server components fetching the API with forwarded cookies: more moving parts for no security gain, since the API enforces every request anyway. Redirecting RSC prefetches in the proxy broke client navigation after sign-out. |
| Frontend data fetching | Small `useAsync` hook + typed client; no SWR/React Query yet | A caching library: unnecessary at Stage 1 scale. |
| CSRF | SameSite=Lax cookie + required `X-VIA-Request: 1` header on unsafe methods for cookie-authenticated requests | Double-submit tokens — unnecessary given same-origin + custom header. |
| PCB viewer | **Canvas 2D**, rendered from a viewer-specific *render model* derived from the normalized JSON (`apps/web/lib/pcb/render-model.ts`); geometry cached as Path2D per layer and stroke width; snapshot previews while interacting on very large boards | SVG (the original plan): one DOM node per primitive, which fails at 100k+ tracks. WebGL: fastest, much more code; the render-model boundary keeps it possible later. |
| AI providers | Interface in `via_ai`, disabled default, optional Anthropic adapter on the official SDK; consent-gated context built by the API | Calling a vendor SDK from features directly: no single place to enforce disabled-by-default, consent and no-fabrication rules. |
| Object storage | `StorageBackend` interface with S3 (boto3; MinIO in dev) and local-filesystem implementations | Storing files in Postgres — explicitly disallowed. |
| Authorization | Central `authorize(user, project, action)` in the API service layer; roles `owner/editor/viewer`; projects private by default; organization and project membership enforced independently (see DATABASE.md) | Postgres RLS — valuable later, adds complexity now. |
| Enum columns | `VARCHAR + CHECK` | Native Postgres enums: adding values requires special migration handling. |
| Migrations | Hand-reviewed Alembic autogenerate; `alembic check` + a parity test in CI | Raw SQL migrations: no model parity check. |
| Local MinIO | Built from official source (`github.com/minio/minio` at a pinned commit, via the Go module proxy) in `infrastructure/docker/minio.Dockerfile`; prebuilt image optional via `MINIO_IMAGE` | `minio/minio` on Docker Hub is no longer published; `quay.io` isn't reachable from every network; community forks are third-party code. |
| Builds behind TLS-intercepting proxies | Optional BuildKit secret `build_ca` (`VIA_BUILD_CA_CERT`), applied only when non-empty and never stored in a layer | Baking a CA into images: leaks environment-specific trust into production artefacts. |
| Integration tests | Real Postgres/Redis/MinIO via `VIA_TEST_*` env; skip locally when absent, **fail** when `CI=true` | SQLite/mocks: would not catch Postgres-specific behaviour (JSONB, CHECK, cascades). |

## 4. Data model (implemented in CP2, details in DATABASE.md)

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

## 5. Request flow: PCB import (implemented in CP4)

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
| 5 | ~~Pad/graphic transform semantics~~ | — | **Resolved in CP2:** investigated on real KiCad 5.1-9.0 boards (docs/ENGINEERING.md). Pad angles are absolute; a missing angle means 0 (bug fixed). Positions confirmed by a track-endpoint electrical check. |
| 6 | **Sandboxed build environment** (TLS-intercepting proxy, no `quay.io`) | Image builds fail without workarounds | Optional `build_ca` build secret; MinIO built from pinned source. The committed Compose file needs no sandbox-specific settings. |
| 7 | **Bleeding-edge frontend stack** (Next 16, React 19, Tailwind 4) | Integration friction | Exact pins; shadcn components vendored into `packages/ui` rather than generated at install time. |
| 8 | **Scope creep** | Stage 1 never finishes | Coming-soon states for non-Stage-1 sections; no fabricated data or AI output. |

## 7. Dependencies

Exact versions are pinned everywhere: `pyproject.toml` (direct), `apps/api/requirements.lock`
(all transitive Python deps for images), `pnpm-lock.yaml` (JS). JS versions were chosen to
be at least two weeks old at the time of pinning.

| Dependency | Why |
|---|---|
| fastapi, uvicorn[standard] | HTTP API + ASGI server |
| pydantic, pydantic-settings | Schemas; settings from env |
| sqlalchemy, psycopg[binary] | ORM / Postgres driver |
| alembic | Migrations |
| redis | Rate limiting; readiness; job queue |
| rq | Background job queue (worker) |
| python-multipart | Multipart parsing for uploads (required by FastAPI `UploadFile`) |
| argon2-cffi | Argon2id password hashing |
| boto3 | S3-compatible storage (MinIO, AWS S3) |
| httpx2 (dev) | Starlette 1.10's test client (plain `httpx` is deprecated there) |
| next, react, react-dom | Web app |
| tailwindcss, @tailwindcss/postcss | Styling via design tokens |
| class-variance-authority, clsx, tailwind-merge, @radix-ui/react-slot | Component variants and composition (shadcn approach, vendored components) |
| @radix-ui/react-dialog, -tooltip, -dropdown-menu | Accessible overlay primitives (focus trap, keyboard, ARIA) |
| @testing-library/user-event (dev) | Realistic interaction in form tests |
| anthropic (optional extra of via-ai-engine) | Anthropic provider adapter; not installed by default or in images |
| lucide-react | Icons |
| vitest, vite, jsdom, @testing-library/react (dev) | Frontend unit/component tests |
| @playwright/test (dev) | End-to-end browser tests against the running stack |
| eslint 9 + eslint-config-next | Linting (ESLint 10 is not yet supported by Next's plugins) |


Regenerating the Python lock:

```bash
printf -- "-e ./services/pcb-engine\n-e ./apps/api\n" > /tmp/req.in
uv pip compile /tmp/req.in --python-version 3.13 --no-emit-package via-pcb-engine --no-emit-package via-api --no-header -o apps/api/requirements.lock
```
(then delete the `-e` lines and keep the two header comment lines).
