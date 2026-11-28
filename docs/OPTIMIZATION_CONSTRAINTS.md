# VIA Optimize: constraints, ranking and candidate lifecycle

Status: Phase 3, Checkpoint 3 (optimization core). Code: `services/optimization/src/via_opt/{rules,constraints,modules,ranking,lifecycle,validation}.py`.
Overview of the engine: [OPTIMIZATION_ENGINE.md](OPTIMIZATION_ENGINE.md).

## Constraints
Every candidate is applied to a copy of the design and each constraint is evaluated on (original, modified)
(`via_opt.rules.evaluate`). Results are stored with the candidate (`validation.constraints`, returned as
`constraints_evaluated`).

| Result | Meaning |
|---|---|
| `satisfied` | Checked and met |
| `violated` | Checked and broken: the candidate **fails** validation |
| `unverified` | VIA can't check it. **Never counted as satisfied** |
| `not_applicable` | The change can't affect it (e.g. overlap for an outline-only change) |

**Hard constraints** (built in): `component_identity`, `net_connectivity` (netlist unchanged; not routed continuity),
`fixed_components`, `within_outline`, `edge_margin`, `component_overlap`, `keepout_zones`, `board_size`,
`outline_fixed`, and `routed_connectivity` (`unverified` when routed parts move: they must be re-routed).
Closeness that already existed before the change (a part already near the edge or another part) is not blamed on
the candidate; a change may not make it worse.

**Soft preferences** are the objectives (area, placement, routing, cost, layers, thermal, manufacturability) and
their optional weights. A weight can order candidates; it can never override a hard constraint.

**Declared requirements.** `constraints.requirements[]` (`kind`, `description`, `hard`) lets an engineer state something
VIA can't evaluate (impedance, length matching, enclosure fit...). It is recorded as `unverified`. A hard one stops
the candidate being validated (validation status `unverified`, lifecycle `needs_review`); a soft one is recorded only.
Unknown kinds are accepted, not rejected, and never silently satisfied.

## Validation status
`failed` (a hard constraint violated, or a new medium-or-worse problem found by VIA's checks) > `requires_rerouting`
> `unverified` (declared hard requirement) > `passed`. `manual` for changes VIA can't apply. "Passed" means VIA's own
checks and the constraints above; KiCad DRC runs only after a change set is applied.

## Lifecycle (derived; stored statuses are unchanged)
| `lifecycle` | From |
|---|---|
| `validated` | status `validated` |
| `validation_failed` | rejected by the engine (failed validation) |
| `needs_review` | awaiting re-routing, an unverified requirement, or a manual change |
| `accepted` | a person accepted it (only validated candidates can be) |
| `applied` | accepted and included in an applied change set |
| `rejected` | a person rejected it, with a reason |

"Generated" and "evaluating" are run states (`queued`, `running`, with `summary.phase`): candidates are stored only
once evaluated.

## Weighted preference (`weights`, optional)
Lower is better. Score = sum(weight x relative change) / sum(weights), over weighted objectives whose metric is known
before and after. Relative change = (after - before) / before when before > 0. When before is 0 the relative change
is undefined: that metric is left out and the score is marked `partial` (with the reason in `excluded`). Failed
candidates are never ranked. Weights never change status or the Pareto front. Weights are accepted only for requested
objectives, between 0 and 1000.

## Module declarations
`GET /api/v1/optimization-modules` lists every module with `status` (`implemented`, `partial`, `planned`,
`unsupported`), what it `understands`, `requires`, `cannot_evaluate` and `preserves`, and its limitations. Planned and
unsupported capabilities are listed so nothing is implied to work that doesn't.

## Candidate record
Besides the change set, metrics before/after, benefits and trade-offs: `constraints_evaluated`, `warnings`,
`limitations`, `execution` (deterministic, seed, evaluation time; never used for equality), `score`, `lifecycle` and
`candidate_hash` (sha256 of algorithm, version and canonical changes: identical inputs give an identical hash). The
candidate design is never stored as a file: it is `apply(original, changes)`, deterministic and isolated, and is only
written out when a change set is applied as a new revision.
