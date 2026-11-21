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

## Out of scope for Stage 1
AI-generated analysis, DRC/optimization, PCB editing, VIA Learn contribution,
non-KiCad formats, enterprise organization management (SSO, billing, advanced roles).

## Product principles
- Honest software: never fabricate data, statistics or AI results.
- Private by default: user designs are never shared, used for training or sent to
  third-party models without an explicit, authorized action.
- Engineering correctness over appearance of completeness.
