# VIA

VIA is an AI-native collective engineering platform. Stage 1 focuses on **PCB
design intelligence**: ingesting real PCB files into a normalized, tool-agnostic
model, then exploring them in a secure, project-based workspace.

> **Status: Stage 2 complete (all 8 milestones; see [docs/STAGE_2_ACCEPTANCE.md](docs/STAGE_2_ACCEPTANCE.md)).** Stage 1 is complete:
> accounts, projects, sharing, the PCB pipeline and an interactive board viewer, covered by unit,
> integration, security and browser tests. Stage 2 so far adds KiCad project (`.zip`) import with
> design rules, schema 1.1 (stable object ids, stackup, locks), job recovery after worker crashes, and
> the analysis/findings framework with KiCad 9's real DRC and VIA's geometry, manufacturing,
> placement and routing checks, and grounded AI explanations and reviews (disabled until a provider
> is configured), validated optimization candidates, and change sets that patch your original KiCad file in place, verify
> it and import it as a new revision with rollback and comparison, all usable from the design workspace
> (Analysis, Optimize and Changes tabs, with finding overlays on the board).
> See [docs/ROADMAP.md](docs/ROADMAP.md) and [docs/STAGE_2_AUDIT.md](docs/STAGE_2_AUDIT.md).

## What works today

- **PCB engine** (`services/pcb-engine`): parses KiCad `.kicad_pcb` files into the
  normalized `PCBDesign` model. Validated against real boards from KiCad 5.1, 6.0,
  7.0, 8.0 and 9.0 (see [docs/ENGINEERING.md](docs/ENGINEERING.md) for exactly what is
  and isn't covered).
- **Accounts:** register, sign in/out, password reset, profile, password change,
  signed-in devices. Argon2id passwords, server-side sessions, CSRF protection,
  rate limits, audit log.
- **Projects:** create, rename, describe, archive/restore, delete, search and filter;
  private by default; share with other users as editor or viewer.
- **PCB upload:** drag and drop a KiCad project `.zip` (board + `.kicad_pro`/`.kicad_dru`, so its design rules and net classes come along) or a bare `.kicad_pcb` file (up to 50 MB). It's validated
  (type, size, duplicate by SHA-256), stored in object storage and parsed in the
  background by a worker in a credential-free, resource-limited sandbox.
- **Design pages:** board dimensions, layers, counts, source metadata, parser warnings,
  searchable components, nets and layers, revisions, original file download.
- **Board viewer:** see the real parsed board: toggle layers, zoom and pan, fit,
  click or search components and inspect their properties and pad nets.
- **AI foundation:** provider interfaces, disabled unless configured; project data is
  only usable with the project owner's explicit consent.
- **Dashboard, project workspace and activity feed** built on real data only.
- **API** (`apps/api`): versioned REST API with OpenAPI docs, consistent errors, the full
  Stage 1 schema with Alembic migrations, S3-compatible storage (MinIO locally).

## Prerequisites

| Tool | Version | Used for |
|---|---|---|
| Docker + Compose v2 | recent | Full stack |
| Python | 3.13 (3.12+ works) | API, PCB engine, tests |
| [uv](https://docs.astral.sh/uv/) | 0.5+ | Python environments |
| Node.js | 22 LTS (≥ 22.12) | Web app |
| pnpm | 10.28 (`corepack enable`) | JS workspaces |

## Option A: run everything with Docker Compose

```bash
cp .env.example .env
```

Edit `.env` and replace every `change-me` value (`VIA_SECRET_KEY`, `POSTGRES_PASSWORD`,
`MINIO_ROOT_PASSWORD`). Compose refuses to start without them. Then:

```bash
docker compose up --build
```

The first build compiles MinIO from source and takes a few minutes. When it's up:

| What | URL |
|---|---|
| Web app | http://localhost:3000 (create an account at `/register`; system status: `/status`) |
| API docs (OpenAPI) | http://localhost:8000/api/docs |
| API readiness | http://localhost:8000/api/v1/health/ready |
| MinIO console | http://localhost:9001 (user `MINIO_ROOT_USER`, password `MINIO_ROOT_PASSWORD`) |

Services: `postgres`, `redis`, `minio`, `migrate` (one-shot: applies migrations and
verifies storage, then exits), `api`, `worker` (parses uploads, runs analyses), `eda` (KiCad 9 for
DRC; the image is ~2.3 GB on first build), `web`. All host ports
bind to `127.0.0.1`.

Behind a corporate TLS-intercepting proxy, set `VIA_BUILD_CA_CERT=/path/to/ca.pem` in
`.env` so image builds can reach package registries.

Password reset emails aren't delivered in Stage 1: in development the API logs them,
link included (`docker compose logs api | grep -A8 EMAIL`).

Stop with `docker compose down` (add `-v` to delete the database and stored files).

## Option B: develop natively

Run only the infrastructure in Docker:

```bash
docker compose up -d postgres redis minio migrate
```

Python environment:

```bash
uv venv .venv --python 3.13
```

```bash
uv pip install --python .venv/bin/python -r apps/api/requirements.lock
```

```bash
uv pip install --python .venv/bin/python -e services/pcb-engine -e services/ai-engine -e services/eda-runner -e services/optimization -e "apps/api[dev]"
```

Start the API with auto-reload. Export the native-run variables from `.env.example`
first (`VIA_DATABASE_URL`, `VIA_REDIS_URL`, `VIA_S3_*`), using your `.env` passwords:

```bash
.venv/bin/via-api serve --reload
```

In a second terminal (same variables), start the worker that parses uploads:

```bash
.venv/bin/via-api worker
```

Web app (proxies `/api/*` to `VIA_API_INTERNAL_URL`, default `http://localhost:8000`):

```bash
pnpm install
```

```bash
pnpm dev
```

## Tests and checks

Python lint, format and types:

```bash
.venv/bin/ruff check . && .venv/bin/ruff format --check . && .venv/bin/mypy services/pcb-engine/src services/ai-engine/src services/eda-runner/src services/optimization/src apps/api/src
```

Python tests. Integration tests need Postgres, Redis and MinIO: with the Compose stack
running, export the `VIA_TEST_*` variables from `.env.example` (they point at the Compose
services and the `via_test` database). Without them, those tests are reported as skipped:

```bash
.venv/bin/pytest -ra
```

Real-board engineering tests need the KiCad demo boards (CC BY-SA, downloaded to a
git-ignored folder, never committed):

```bash
.venv/bin/python scripts/fetch_real_fixtures.py
```

Frontend lint, types, tests and production build:

```bash
pnpm lint && pnpm typecheck && pnpm test && pnpm build
```

End-to-end browser tests (Playwright, Chromium) run against the full Compose stack, so
start it first (`docker compose up -d --build`):

```bash
pnpm --filter @via/web exec playwright install chromium
```

```bash
pnpm --filter @via/web e2e
```

Set `E2E_BASE_URL` to test another deployment. Each run registers a few users; the
registration limit is 10 per IP per hour, so for many local reruns clear the limits with
`docker compose exec redis redis-cli FLUSHALL` (development only).

CI (`.github/workflows/ci.yml`) runs all of the above with real services, with
`CI=true` so missing services fail the build instead of skipping tests, builds the
Docker images, starts the stack and runs the end-to-end suite against it.

## Before exposing VIA to the internet

Stage 1 is built to run locally. A public deployment additionally needs, at minimum:

- **A reverse proxy in front of the web app that overwrites `X-Forwarded-For`** with the
  real client address (Caddy does by default; with nginx use
  `proxy_set_header X-Forwarded-For $remote_addr`). Never expose port 3000 directly:
  Next.js forwards a client-supplied `X-Forwarded-For` unchanged, and the API uses it for
  per-IP rate limits (see docs/SECURITY.md). HTTPS terminates at that proxy.
- `VIA_ENV=production` (enforces a strong secret key, no wildcard CORS, no bucket auto-creation).
- An email provider for password resets (Stage 1 has none).
- Backups of the Postgres and MinIO volumes.

## Parse a board from the command line

```bash
.venv/bin/python -c "from via_pcb import parse_pcb; d = parse_pcb('tests/engineering/fixtures/via_reference_v8.kicad_pcb'); print(d.stats.model_dump_json(indent=2))"
```

## Documentation

- [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md): system design, decisions, risks, dependencies
- [docs/DATABASE.md](docs/DATABASE.md): schema, migrations, authorization model, VIA Learn readiness
- [docs/API_SPEC.md](docs/API_SPEC.md): API conventions, error format, endpoints
- [docs/ENGINEERING.md](docs/ENGINEERING.md): PCB engine, KiCad support and validation
- [docs/SECURITY.md](docs/SECURITY.md): security and privacy design
- [docs/ROADMAP.md](docs/ROADMAP.md): checkpoints and later stages
- [docs/PRD.md](docs/PRD.md): product requirements
- [docs/STAGE_2_AUDIT.md](docs/STAGE_2_AUDIT.md): Stage 2 audit and plan
- [docs/FINDINGS_SYSTEM.md](docs/FINDINGS_SYSTEM.md): analysis findings contract, provenance, review, comparison
- [docs/PCB_ANALYSIS.md](docs/PCB_ANALYSIS.md): analysis checks and what they do and don't cover
- [docs/AI_INTELLIGENCE.md](docs/AI_INTELLIGENCE.md): AI features, grounding verification, consent, audit
- [docs/OPTIMIZATION_ENGINE.md](docs/OPTIMIZATION_ENGINE.md): objectives, constraints, candidates, validation, Pareto comparison; also [architecture](docs/OPTIMIZATION_ARCHITECTURE.md), [algorithms](docs/OPTIMIZATION_ALGORITHMS.md), [API](docs/OPTIMIZATION_API.md), [roadmap](docs/OPTIMIZATION_ROADMAP.md)
- [docs/OPTIMIZATION_CONSTRAINTS.md](docs/OPTIMIZATION_CONSTRAINTS.md): hard constraints, declared requirements, weighted preference, lifecycle
- [docs/STAGE_2_ACCEPTANCE.md](docs/STAGE_2_ACCEPTANCE.md): the 14 Stage 2 acceptance criteria mapped to tests, measurements and limits
- [docs/CHANGE_MANAGEMENT.md](docs/CHANGE_MANAGEMENT.md): change sets, in-place export and its verification, lineage, rollback, comparison
