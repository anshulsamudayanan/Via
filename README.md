# VIA

VIA is an AI-native collective engineering platform. Stage 1 focuses on **PCB
design intelligence**: ingesting real PCB files into a normalized, tool-agnostic
model, then exploring them in a secure, project-based workspace.

> **Status: Stage 1, Checkpoint 1 of 6.** The PCB engine core is built and tested.
> The API, web app and Docker stack come in Checkpoints 2 to 6. See
> [docs/ROADMAP.md](docs/ROADMAP.md). This README only describes what works today.

## What works today

- `services/pcb-engine`: parses KiCad 5–9 `.kicad_pcb` files into the normalized
  `PCBDesign` model: outline, dimensions, layers, nets, footprints, pads, tracks,
  vias, zones, graphics and in-file constraints, plus warnings for anything it
  can't parse. See [docs/ENGINEERING.md](docs/ENGINEERING.md).

## Prerequisites

| Tool | Version | Used for |
|---|---|---|
| Python | 3.12+ (3.13 recommended) | API, worker, PCB engine |
| [uv](https://docs.astral.sh/uv/) | 0.5+ | Python environments |
| Node.js | 22 LTS | Web app (from CP2) |
| pnpm | 9+ | JS workspaces (from CP2) |
| Docker + Compose v2 | recent | Full stack (from CP2) |

## Run the PCB engine and its tests

```bash
uv venv .venv --python 3.13
```

```bash
uv pip install --python .venv/bin/python -e services/pcb-engine pytest==9.2.0 ruff==0.17.6 mypy==2.4.1
```

```bash
.venv/bin/pytest
```

Parse a board from the command line:

```bash
.venv/bin/python -c "from via_pcb import parse_pcb; d = parse_pcb('tests/engineering/fixtures/via_reference_v8.kicad_pcb'); print(d.stats.model_dump_json(indent=2))"
```

Lint and type checks:

```bash
.venv/bin/ruff check . && .venv/bin/ruff format --check . && .venv/bin/mypy services/pcb-engine/src
```

## Running the full application (target, from CP2)

```bash
cp .env.example .env
```

```bash
docker compose up --build
```

Web: http://localhost:3000 · API docs: http://localhost:8000/api/docs

## Documentation

- [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md): system design, decisions, risks
- [docs/ROADMAP.md](docs/ROADMAP.md): checkpoints and later stages
- [docs/ENGINEERING.md](docs/ENGINEERING.md): PCB engine and KiCad support matrix
- [docs/SECURITY.md](docs/SECURITY.md): security and privacy design
- [docs/PRD.md](docs/PRD.md): product requirements
