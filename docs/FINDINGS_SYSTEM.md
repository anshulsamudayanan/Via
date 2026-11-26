# VIA Findings System

Status: Stage 2, Milestone 2. The framework is complete. Its four checks are deliberately simple and exact.
KiCad DRC and VIA's full deterministic checks arrive in Milestone 3, AI suggestions in Milestone 4.

Every analysis result in VIA, whatever produced it, is a **finding** with the same structure,
stored with exactly what produced it, and reviewable by people. This document defines that contract.

## The finding

Engine schema: `services/pcb-engine/src/via_pcb/analysis/findings.py`. Stored in `analysis_findings`
plus `finding_evidence`; API shape `FindingOut` / `FindingDetail`.

| Field | Meaning |
|---|---|
| `id`, `run_id`, `project_id`, `design_id`, `revision_id` | Identity and the exact revision analysed |
| `check_id`, `check_version`, `rule` | Which check (and which version of its logic) and which specific rule fired |
| `category` | `geometry`, `board_outline`, `design_rules`, `connectivity`, `routing`, `placement`, `manufacturing`, `thermal`, `power`, `signal_integrity`, `import` |
| `severity` | `critical`, `high`, `medium`, `low`, `info` |
| `title`, `description` | What was found, specific to this design |
| `explanation` | Why it matters (engineering background) |
| `objects` | `[{kind, id, label}]`: components, pads, tracks, vias, zones, nets, the outline or layers, by their **stable ids** in the normalized design (schema 1.1). The viewer uses them to navigate (Milestone 7) |
| `components`, `nets` | Reference designators and net names involved (filterable, searchable) |
| `region` | `{bbox, points, layers}` in board millimetres, when the finding has a location; `points` are exact markers (e.g. unjoined outline endpoints) |
| `source` | Where it came from (below). Shown with every finding |
| `verification` | How far the finding itself can be trusted, as produced (below) |
| `confidence` | 0–1. 1.0 for exact computations; lower for heuristics and hypotheses |
| `evidence` | `[{kind, label, value, numeric_value, unit, expected}]`. `kind` ∈ `measurement`, `rule`, `source_data`, `tool_output`, `reference` |
| `suggested_resolution` | What to do about it, when there is a clear action |
| `fingerprint` | Identifies "the same issue" across revisions (below) |
| `status`, `status_reason`, `status_changed_at`, `inherited` | Review state (below) |

### Sources: who said so

| `source` | Meaning | Can be `verified`? |
|---|---|---|
| `via_deterministic` | VIA's own algorithm on the parsed design | Yes, when the computation is exact on data the model represents exactly; otherwise `heuristic` |
| `kicad_drc` | KiCad's own design rule checker (Milestone 3) | Yes. It is KiCad's result, reported as KiCad's, never as VIA's |
| `external_simulation` | A simulator's output | Labelled as simulated |
| `ai_suggestion` | A language model (Milestone 4) | **Never** by itself: `unverified` until a deterministic check or a person confirms it |

The engine refuses findings attributed to a different check or source than the check that
produced them: the check is marked `error`, and its findings are dropped.

### Verification vs review

- **Verification** describes the finding as produced:
  - `verified`: an exact computation, or KiCad DRC.
  - `heuristic`: deterministic, but a rule of thumb or approximate geometry; needs engineering judgement.
  - `unverified`: a hypothesis, e.g. from AI.
- **Review** is what a person decided: `open` → `reviewed` / `dismissed` (a reason is required) → `open` again. Every change is appended to `finding_review_events` with actor, reason and time. Findings themselves are never edited.

### Evidence rules

Evidence is measured from the design, quoted from a rule, or quoted from a tool, never invented.
A value whose unit isn't known isn't converted. Where the model approximates (e.g. pad shapes
drawn as bounding rectangles), the check says so and its findings are `heuristic`.

## Runs and provenance

An **analysis run** (`analysis_runs`, `kind = pcb_analysis`) analyses one revision and records:

- **Versions:** `analysis_version` (finding schema and engine framework), `engine_version`, and the analysed design's `design_parser_version` and `design_schema_version`.
- **`checks`:** each check's id, version, status (`ok`, `skipped` with a reason, `error` with the exception type only), finding count and duration.
- **`config`:** e.g. selected checks.
- **Timing and attempts:** timings, `attempt`, `triggered_by`.

Runs are **immutable history**. Re-running creates a new run; old runs and their findings stay.
Designs parsed before schema 1.1 (no object ids) are re-imported with the current parser before
analysis; the run records the parser version actually used.

Runs execute on the worker (`via_api.jobs.analyze_run`) with the same recovery as imports:
heartbeats, a reaper that retries stale or lost runs up to `VIA_JOB_MAX_ATTEMPTS`, then
`worker_lost`. Starting an identical analysis while one is queued or running returns that run
(idempotent). Starts are rate limited (60/h per user).

## Same issue across revisions: fingerprints

`fingerprint = sha256(check_id | rule | key)[:32]`. The key defaults to the sorted ids of the
objects involved; checks may supply a semantic key (e.g. component id plus pad numbers). The key
must not include values that change when the issue is fixed, such as a measured gap. KiCad keeps
object UUIDs across edits, so the same track or pad keeps its id from one revision to the next.

Two uses:
- **Compare** (`GET /designs/{id}/analysis-compare?base_run_id=&target_run_id=`): `new` (only in the target), `resolved` (only in the base), `persisting` (both; shown as in the target). Both runs must be finished runs of the same design.
- **Review carry-over:** when a new run reports an issue whose latest human decision (any earlier run of the same design) was `reviewed` or `dismissed`, the new finding starts in that state, with `inherited: true` and a `carried_over` history event naming the revision. Reopening is always possible, and a reopened decision isn't carried over.

## API

See docs/API_SPEC.md "Analysis". Summary:

- `GET /analysis/checks`;
- `POST|GET /designs/{id}/analysis-runs`;
- `GET /analysis-runs/{id}`;
- `GET /analysis-runs/{id}/findings` (filters `severity`, `category`, `source`, `verification`, `status`, `check_id`, `component`, `net`, `q`; `sort`, `order`; paging; facet counts);
- `GET /findings/{id}`;
- `POST /findings/{id}/review`;
- `GET /designs/{id}/analysis-compare`.

Reading needs viewer access; starting and reviewing need editor access. Inaccessible things answer `404`.

## Adding a check

1. Subclass `Check` (`via_pcb/analysis/registry.py`): `id`, `version`, `category`, `title`, `description`, `source`; optional `skip_reason(ctx)`; `run(ctx)` yields `Finding`s with honest `source`, `verification`, `confidence` and evidence.
2. Register it in `via_pcb.analysis.default_registry()`.
3. Test it on fixtures with **hand-derived** expectations (`tests/engineering/test_analysis_checks.py`), including a clean case that must produce nothing.
4. Document it in docs/PCB_ANALYSIS.md. Bump `version` whenever logic or thresholds change.
