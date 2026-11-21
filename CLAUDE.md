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
.venv/bin/pytest                                   # Python tests (unit, engineering, integration)
.venv/bin/ruff check . && .venv/bin/ruff format --check .
.venv/bin/mypy services/pcb-engine/src
```

## Tests
- Engineering fixtures need documented provenance and licence (`tests/engineering/fixtures/README.md`). Expected values are derived by hand, not copied from parser output.
- A checkpoint is done only when lint, types and tests pass.
