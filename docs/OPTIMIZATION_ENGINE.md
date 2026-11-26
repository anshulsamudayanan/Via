# VIA Optimize

Status: Stage 2, Milestone 5. Package: `services/optimization` (`via_opt`); API:
`apps/api/src/via_api/{services/optimizer.py,routes/optimization.py}`.

VIA Optimize proposes **explicit, measured, validated change sets**. It never edits the original
design. Accepting a candidate records a decision; a change set (docs/CHANGE_MANAGEMENT.md) turns
accepted, exportable changes into a new revision and an exported KiCad file.

## Pipeline
1. **Baseline metrics** for the parsed design.
2. **Generators** for the requested objectives produce change sets that respect the constraints.
3. **Each candidate is applied to a copy** of the design (`via_opt.changes.apply`), measured with the same metrics, and **validated**:
   - VIA re-runs its manufacturing, outline, board-space and connectivity checks on the modified design;
   - a new medium-or-worse problem → `failed`;
   - a broken constraint → `failed`;
   - moving routed parts → `requires_rerouting` (it can't be validated until re-routed; the problems VIA sees meanwhile are listed as notes);
   - changes that can't be applied automatically → `manual`.
4. **Candidates are compared** on the Pareto front of the requested objectives. Nothing is ranked as "best"; trade-offs are listed.

Candidate states: `proposed` (manual), `awaiting_validation` (needs re-routing), `validated`, `rejected` (failed validation, or a person rejected it, with a reason), `accepted` (only validated candidates can be accepted).

## Objectives and metrics (all minimized, computed from the design)
| Objective | Metric |
|---|---|
| area | `board_area_mm2`: outline area |
| placement | `ratsnest_mm`: sum over nets of the minimum spanning tree of pad positions |
| routing | `routed_length_mm` (via count reported alongside) |
| cost | `cost_index`: VIA's illustrative relative model, area (cm²) × layer factor (1→0.8, 2→1.0, 4→1.9, 6→2.8, 8→3.8) × feature-class factor (1.0 within VIA conservative, 1.3 needs VIA advanced, 1.6 beyond). **An estimate for comparison, never a quote** |
| layers | `copper_layers_used` |
| thermal | `current_capacity_issues`: IPC-2221 findings for the user's currents (needs `options.power`) |
| manufacturability | `manufacturing_issues`: medium-or-worse manufacturing findings under the profile |

## Generators (deterministic)
| Key | Objectives | What | Validation |
|---|---|---|---|
| `outline_fit` | area, cost | Shrinks a **rectangular** outline to the content (component extents, copper, zones) plus max(edge margin, profile copper-to-edge). Only shrinks; skipped if under 1 % gain, if the outline is fixed or if it isn't rectangular | Full (routing untouched) |
| `via_standardization` | manufacturability, cost | Vias failing the profile (drill, diameter, annular ring) grow to the smallest compliant size on a 0.01 mm grid. Skipped per via when growing would break clearance to other-net copper or the edge limit (reported) | Full |
| `track_min_width` | manufacturability, cost | Tracks below the profile minimum widen as far as clearance and the edge limit allow | Full |
| `power_track_widening` | thermal | Tracks of nets with user currents widen towards the IPC-2221 width (worst layer), within clearance and the edge limit | Full |
| `placement_ratsnest` | placement, routing | Greedy, deterministic local search: each movable component tries moves towards the centroid of what it connects to (100/75/50/25 %), keeping inside the outline with the margin, clear of other components (gap) and of footprint keep-outs. Accepted only if the ratsnest shortens | `requires_rerouting` when moved parts carry routed nets |
| `layer_reduction` | layers, cost | When copper layers carry no routing (only through-hole pads and vias), proposes a smaller even layer count | `manual`: layer changes are made in KiCad |

## Constraints (never relaxed silently)
`fixed_components`; `keep_locked_fixed` (KiCad-locked parts; default true); `keep_connectors_fixed` (connectors and mounting holes; default true); `outline_fixed`; `edge_margin_mm`; `component_gap_mm`; `max_board_width_mm`/`max_board_height_mm`.

The manufacturing profile's clearance, copper-to-edge and size minimums apply too. Generators that can't meet a constraint don't propose the change, and validation re-checks every candidate.

## Changes
`move_component`, `rotate_component`, `set_track_width`, `move_via`, `set_via_size` and `set_outline_rect` are exportable (Milestone 6). `set_copper_layer_count` is not.

Each change records:
- its target (stable id and source UUID);
- the values before and after;
- the reason and source (`via_optimize`, `user` or `ai_suggestion`);
- the related findings.

## API
| Method | Path | Role |
|---|---|---|
| POST | `/designs/{id}/optimization-runs` `{objectives[], constraints?, options?}` → 202 (identical active run → 200) | editor, 60/h |
| GET | `/designs/{id}/optimization-runs`, `/optimization-runs/{id}` (config, baseline, Pareto keys, notes) | viewer |
| GET | `/optimization-runs/{id}/candidates`, `/optimization-candidates/{id}` (with changes) | viewer |
| GET | `/optimization-runs/{id}/compare?candidates=` (metrics, deltas vs baseline, Pareto front, dominance) | viewer |
| POST | `/optimization-candidates/{id}/decision` `{status: accepted\|rejected, reason?}` (`409 not_validated`, `422 reason_required`) | editor |

Runs are `analysis_runs` with `kind = pcb_optimization`. They share the worker lifecycle (heartbeat, reaper, retries, `worker_lost`) and snapshot their profile.

## Measured on real boards
- **KiCad 9 `video` demo** with 2 A on `+5V`: 371 power-track widenings, validated (no new problems).
  - Via standardization correctly finds nothing to change: its 0.889/0.4 mm vias meet VIA conservative.
  - A placement candidate is proposed and marked `requires_rerouting`.
- **Reference board:** the outline already fits, so no area candidate.

## Limitations
- No autorouter: placement candidates can't be validated electrically until re-routed in KiCad.
- Only rectangular outlines are resized.
- Optimization doesn't rotate parts yet (rotation changes are supported by the change model and export).
- Thermal optimization covers track width for given currents only.
