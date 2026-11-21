# VIA

VIA is an AI-native collective engineering platform. Stage 1 focuses on **PCB
design intelligence**: ingesting real PCB files into a normalized, tool-agnostic
model, then exploring them in a secure, project-based workspace.

> **Status: Stage 1, Checkpoint 4 of 6.** Accounts, projects, sharing, and the PCB
> pipeline work end to end: upload a KiCad board, it's validated and parsed in an
> isolated worker, and you can browse its board information, components, nets and
> layers. The interactive board viewer arrives in Checkpoint 5.
> See [docs/ROADMAP.md](docs/ROADMAP.md). This README only describes what works today.

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
- **PCB upload:** drag and drop a `.kicad_pcb` file (up to 50 MB). It's validated
  (type, size, duplicate by SHA-256), stored in object storage and parsed in the
  background by a worker in a credential-free, resource-limited sandbox.
- **Design pages:** board dimensions, layers, counts, source metadata, parser warnings,
  searchable components, nets and layers, revisions, original file download.
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
verifies storage, then exits), `api`, `worker` (parses uploads), `web`. All host ports
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
uv pip install --python .venv/bin/python -e services/pcb-engine -e "apps/api[dev]"
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
.venv/bin/ruff check . && .venv/bin/ruff format --check . && .venv/bin/mypy services/pcb-engine/src apps/api/src
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

CI (`.github/workflows/ci.yml`) runs all of the above with real services, with
`CI=true` so missing services fail the build instead of skipping tests, and also
builds the Docker images.

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
