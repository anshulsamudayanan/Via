# VIA — Product Requirements (Stage 1)

## Vision
VIA connects engineering projects, design data, AI, simulations, components and
collective knowledge. Long term it is both an independent engineering
environment (with a native PCB editor, *VIA Studio*) and an intelligence layer
over existing tools (*VIA Connect*). The long-term differentiator is *VIA Learn*:
privacy-first, opt-in collective engineering intelligence.

## Users
Students, hobbyists, freelance PCB designers, professional engineers, engineering
teams, semiconductor companies.

## Stage 1 goal
A secure, project-based workspace where a user can upload a KiCad PCB, have it
validated and parsed into VIA's normalized model, and inspect the real board:
its information, components, nets, layers and an interactive visual view.

## Stage 1 acceptance criteria
A user can:
1. Register and log in.
2. Create a project.
3. Edit project information.
4. Upload a supported KiCad PCB file.
5. Have the file validated and parsed.
6. See board information.
7. See extracted components.
8. See extracted nets.
9. See board layers.
10. View the actual PCB visually.
11. Select components and inspect their properties.
12. Access their project again after logging out and back in.
13. Receive understandable errors when uploads or parsing fail.

Plus: migrations work, Docker Compose starts the services, automated tests exist
(including private-project isolation), README and `.env.example` are complete, and
no secrets are committed.

## Acceptance verification (end of Stage 1)
| # | Criterion | Verified by |
|---|---|---|
| 1 | Register and log in | e2e `core-flow.spec.ts`; `test_auth.py` |
| 2 | Create a project | e2e `core-flow.spec.ts`; `test_projects.py` |
| 3 | Edit project information | e2e `core-flow.spec.ts` (description); `test_projects.py` (rename, visibility, archive) |
| 4 | Upload a supported KiCad PCB file | e2e `core-flow.spec.ts`; `test_pcb_import.py` |
| 5 | File validated and parsed | e2e `core-flow.spec.ts` (worker parses in the sandbox); `test_pcb_import.py`, `test_parser_sandbox.py`, engineering tests on real KiCad 5.1–9.0 boards |
| 6 | See board information | e2e `core-flow.spec.ts`; `test_upload_parses_and_exposes_board_data` |
| 7 | See extracted components | e2e `core-flow.spec.ts` (R1, C1, J1, H1); `test_components_nets_and_layers` |
| 8 | See extracted nets | e2e `core-flow.spec.ts` (VCC, SIG, GND) |
| 9 | See board layers | e2e `core-flow.spec.ts` (F.Cu, B.Cu) |
| 10 | View the actual PCB visually | e2e `core-flow.spec.ts` (embedded and full-page viewer); `board-viewer.test.tsx`, render-model tests |
| 11 | Select components and inspect properties | e2e `core-flow.spec.ts` (search → select R1 → pads; Escape clears) |
| 12 | Access the project again after logging out and in | e2e `core-flow.spec.ts`; `test_access_survives_logout_and_login` |
| 13 | Understandable upload and parse errors | e2e `uploads.spec.ts` (wrong type, spoofed content, duplicate, parse failure); `test_invalid_uploads_are_rejected_and_recorded` |
| — | Migrations work | `test_migrations.py` (upgrade/downgrade/upgrade, model parity); Compose `migrate` service |
| — | Docker Compose starts the services | CI `e2e` job (stack started, readiness checked through the web app, then the browser suite) |
| — | Private-project isolation | `test_security_regression.py` (every route), `test_access_control.py`, `test_pcb_access.py`, e2e `isolation.spec.ts` |
| — | README and `.env.example` complete; no secrets committed | README; `.env.example` placeholders only; `.env` git-ignored |

## Out of scope for Stage 1
AI-generated analysis, DRC/optimization, PCB editing, VIA Learn contribution,
non-KiCad formats, enterprise organization management (SSO, billing, advanced roles).

## Product principles
- Honest software: never fabricate data, statistics or AI results.
- Private by default: user designs are never shared, used for training or sent to
  third-party models without an explicit, authorized action.
- Engineering correctness over appearance of completeness.
