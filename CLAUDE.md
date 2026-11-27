# CLAUDE.md — working on VIA

Read `docs/ARCHITECTURE.md` and `docs/ROADMAP.md` first. Stage 1 is delivered in
checkpoints; do not build features from later checkpoints or stages early.

## Ground rules
- Real functionality only. No hardcoded example data presented as user data, no fabricated stats or AI output. Unbuilt features show an honest "coming soon" state.
- The normalized model (`services/pcb-engine/src/via_pcb/models`) is the contract between the engine and everything else. Never let vendor formats leak past an adapter. Additive changes bump the minor `SCHEMA_VERSION`; breaking changes bump the major.
- Don't claim to parse fields that aren't parsed. Update the support matrix in `docs/ENGINEERING.md` whenever adapter coverage changes.
- Security: authorization is enforced in the API service layer for every project-scoped read and write. Projects are private by default. Uploaded files are never executed and never sent to external services or used for VIA Learn without explicit consent.
- No new dependencies without a reason. Pin exact versions.
- No empty placeholder modules.

## Commands
```bash
.venv/bin/pytest -ra                               # Python tests; integration tests need VIA_TEST_* (see tests/conftest.py)
.venv/bin/ruff check . && .venv/bin/ruff format --check .
.venv/bin/mypy services/pcb-engine/src services/ai-engine/src services/eda-runner/src services/optimization/src apps/api/src
.venv/bin/python scripts/fetch_real_fixtures.py    # real KiCad boards (CC BY-SA, never commit them)
pnpm lint && pnpm typecheck && pnpm test && pnpm build
pnpm --filter @via/web e2e                        # Playwright; needs the Compose stack running
docker compose config --quiet                      # after editing compose or .env.example
cd apps/api && alembic revision --autogenerate -m "..."   # review by hand; `alembic check` must pass
```

## Conventions
- Database: UUID PKs, timestamptz, VARCHAR+CHECK enums, deterministic constraint names. Every schema change ships with a migration; `tests/integration/test_migrations.py` enforces model/migration parity.
- API: everything under `/api/v1`; errors use the envelope in `via_api/errors.py`; project-scoped data returns 404 when the caller lacks access.
- Organization and project membership are independent; never infer project access from organization roles (see docs/DATABASE.md).
- Frontend: only semantic design tokens (`bg-surface`, `text-muted`, `glass-regular`...), never raw colours. Follow docs/DESIGN_SYSTEM.md ("Black Glass"): purple `accent` only for primary action, active and selected states, focus and finding highlights; `Panel`/`Glass` for regions within the blur budget; `Mono` only for engineering identifiers; text on glass must keep 4.5:1. Browser code talks only to same-origin `/api/*`.
- Animation: use Motion (`import { m } from "motion/react"`; `LazyMotion strict` is global, so `m.*`, never `motion.*`), springs from `@via/ui` (`SPRING`...), transform/opacity/filter only, and respect `prefers-reduced-motion` (`useReducedMotion` for loops, tilt and parallax).
- Pin JS versions that are at least two weeks old; Python deps are locked in `apps/api/requirements.lock`.

## Tests
- Engineering fixtures need documented provenance and licence (`tests/engineering/fixtures/README.md`). Expected values are derived by hand, not copied from parser output.
- A checkpoint is done only when lint, types and tests pass.
- New API routes are picked up by `tests/integration/test_security_regression.py`: public routes go in `PUBLIC`, query-scoped ones in `QUERY_SCOPED`, write bodies in `BODIES`, other required query parameters in `QUERY`; new id path parameters go in `ID_PARAMS` (and the `world` fixture).
- Analysis checks: follow docs/FINDINGS_SYSTEM.md "Adding a check". Honest `source`/`verification`, evidence measured not invented, hand-derived tests including a clean case, bump the check `version` on logic changes.
