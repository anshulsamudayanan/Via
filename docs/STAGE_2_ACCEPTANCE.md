# Stage 2 acceptance

Each of the brief's 14 final acceptance criteria, with the evidence that it holds: named automated
tests (run in CI), measurements, and the limitations that remain. Test names are
`file::test` under `tests/` unless marked `e2e` (Playwright, `apps/web/e2e`, against the real
Compose stack in CI).

| # | Criterion | Evidence | Limits |
|---|---|---|---|
| 1 | A real KiCad PCB can be imported | `engineering/test_real_kicad_boards.py` (KiCad 5.1, 6, 7, 8, 9 demo boards: counts vs an independent text scan, electrical consistency); `integration/test_project_import.py::test_project_archive_is_parsed_with_its_design_rules`; e2e `core-flow`, `project-import` | KiCad only; see the support matrix in ENGINEERING.md |
| 2 | VIA can analyse its actual structure | `integration/test_analysis_api.py::test_run_analysis_end_to_end`; `engineering/test_connectivity_and_manufacturing.py`, `test_placement_routing_checks.py`; real-board agreement with KiCad's DRC (`integration/test_kicad_drc_pipeline.py`); e2e `analysis` (KiCad 9.0.6 DRC finds the 15 violations on the reference board) | Zones aren't refilled; no schematic, so no electrical-intent checks (PCB_ANALYSIS.md) |
| 3 | Deterministic findings are generated | Every check in `engineering/test_analysis_checks.py` etc. has hand-derived expected values and a clean case; findings carry `source=via_deterministic`/`kicad_drc` and `verification` (FINDINGS_SYSTEM.md) | Heuristic checks say `heuristic` |
| 4 | Findings contain evidence and affected objects | `engineering/test_kicad_drc_mapping.py::test_shorts_are_critical_and_mapped_to_exact_objects`; `integration/test_analysis_api.py::test_run_analysis_end_to_end` (evidence rows, objects by stable id, region) | |
| 5 | Users can navigate from findings to the board | `apps/web/lib/pcb/overlay.test.ts` (region, component and net highlight drawn), `components/analysis/analysis.test.tsx` (selecting a finding highlights it); e2e `workspace` | Net highlight draws arcs as two chords |
| 6 | AI can explain findings using actual design context | `integration/test_intelligence_api.py::test_explanation_is_grounded_labelled_and_audited`, `::test_invented_references_are_rejected_and_kept_for_audit`, `::test_focus_on_finding_component_and_net`; `unit/ai/test_orchestration.py` (grounding rejects invented parts and numbers) | AI is off until a provider is configured; tests use a scripted provider. Output is always labelled an unverified suggestion |
| 7 | Optimization candidates can be generated | `integration/test_optimization_api.py::test_run_generates_validated_candidates_without_touching_the_design`; `unit/optimization/test_optimizer.py` | Placement moves that need re-routing are marked so, not validated (OPTIMIZATION_ENGINE.md) |
| 8 | Candidates can be compared | `integration/test_optimization_api.py::test_compare_and_pareto` | Cost index is illustrative and labelled as such |
| 9 | Proposed changes can be reviewed | `integration/test_optimization_api.py::test_decisions`; `integration/test_change_sets_api.py::test_validation_conflicts_and_undo` (preview, undo, conflicts); e2e `workspace` | |
| 10 | Supported changes can be validated and exported without silently losing original design data | `engineering/test_patch_export.py::test_empty_change_set_is_byte_identical`, `::test_real_boards_patch_and_verify` (KiCad 5 to 9; only edited lines differ; re-parse verified against the intended changes), `::test_project_archive_only_board_member_changes`, `::test_unknown_targets_and_unsupported_kinds_are_refused_not_guessed`; `integration/test_change_sets_api.py::test_apply_candidate_creates_child_revision_and_patched_file`, `::test_follow_up_analysis_and_comparison`; e2e `workspace` (apply, download, compare, roll back) | Exportable: move, rotate, track width, via move/size, rectangular outline. Layer-count changes are manual (CHANGE_MANAGEMENT.md) |
| 11 | Existing functionality remains intact | The full Stage 1 suites still run unchanged in CI: `integration/test_security_regression.py` (every route: auth, CSRF, cross-user 404s, rate limits), upload, project, sharing and viewer tests; e2e `core-flow`, `isolation`, `uploads` | |
| 12 | Automated tests pass | CI (`.github/workflows/ci.yml`): Python lint, types and tests; web lint, types, unit tests and build; Docker Compose stack with Playwright | |
| 13 | Documentation is updated | New: PCB_ANALYSIS.md, OPTIMIZATION_ENGINE.md, AI_INTELLIGENCE.md, FINDINGS_SYSTEM.md, CHANGE_MANAGEMENT.md, STAGE_2_AUDIT.md, this file. Updated: ARCHITECTURE, API_SPEC, DATABASE, ENGINEERING, SECURITY, ROADMAP, README | |
| 14 | The application runs reliably | Job recovery: `integration/test_job_recovery.py` (killed worker recovered end to end, stale heartbeats, lost jobs, retries, `worker_lost`); concurrency: `integration/test_concurrency.py` (duplicate starts share one run, one apply per design, revision numbers never collide, stale bases refused); failure modes: `integration/test_failure_modes.py` (storage outages in upload, analysis and export; AI provider outage and refusal); rate limits in the security suite; sandbox limits in `unit/api/test_parser_sandbox.py`; performance measured in ENGINEERING.md "Stage 2 performance"; `scripts/load_test.py` for the running stack | See the performance limits in ENGINEERING.md |

## What is deterministic, AI-assisted, simulated or unsupported

- **Deterministic:** parsing; VIA's geometry, connectivity, manufacturing, placement and routing
  checks; KiCad's own DRC; optimization metrics and validation; export and its verification.
- **Estimates from published formulas** (labelled as such, not simulations): IPC-2221 current
  capacity, IPC-2141 microstrip impedance.
- **AI-assisted:** explanations, design reviews and recommendations. Always labelled
  `ai_suggestion` / `unverified`, grounded against the design data, and audited.
- **Simulated:** the change-set preview applies changes to VIA's model, not to the file
  (`source: "simulated"`). No external field solver or SPICE is integrated (`external_simulation`
  is reserved).
- **Unsupported:** formats other than KiCad; schematic-level checks; zone refill; automatic
  re-routing; exporting layer-count changes.
- **Needs engineering validation:** heuristic checks (marked `heuristic`), optimizer placement
  moves (`requires_rerouting`), AI suggestions, and the illustrative cost index.
