# VIA Optimize: algorithms

All algorithms are deterministic. Where randomness is used (annealing) the seed and iteration budget are fixed, so the same design and constraints give the same candidate.

## Outline fit (`outline_fit`)
Shrinks a rectangular outline to the bounding box of component extents, copper and zones plus max(edge margin, profile copper-to-edge). Only shrinks; skipped under 1 % gain, for fixed or non-rectangular outlines.

## Via standardization / track minimum width / power widening
Grow vias or tracks to the smallest compliant (or IPC-2221-required) size on a 0.01 mm grid, skipped per item when growth would break clearance to other-net copper or the edge limit.

## Placement (`placement_ratsnest`, v2.0.0)
- Objective: sum over nets of the minimum spanning tree of pad positions (ratsnest). Nets over 40 pads are ignored while searching.
- Phase 1, descent: each movable part tries moving towards the centroid of what it connects to.
- Phase 2, simulated annealing: seed `20260128`, at most 20 000 iterations and 300 per part, 20 s safety cap (reported as `budget_exhausted`). Moves are shifts and quarter-turn rotations of top-side parts; a part is moved or rotated, not both, in one candidate (one change per target).
- Hard constraints (outline and edge margin, overlap, keep-outs, fixed parts, board size) **reject** a move; they are never traded against cost.
- Uniform spatial grid for neighbour queries.
- `placement_compaction`: the placement result with the outline fitted to it; offered only when it is smaller than the plain fit.
- Routed parts that move make the candidate `requires_rerouting`; VIA has no autorouter.

## Area analysis
Rasterises part extents. Occupied area uses centre-based fill; the empty-rectangle search uses inclusive (conservative) fill. Largest empty rectangle by the histogram method, clipped to the outline. Also a 6x6 density grid and unused margin per side.

## Margin analysis
Re-runs the manufacturing checks with each `min_*` inflated by 25 %. Compares distinct features: those violating the profile versus those that only violate the inflated limit ("potential risk", a VIA heuristic, not a fabricator statement).

## Ranking
`score = sum(weight x relative change) / sum(weights)` over the weighted objectives. A zero baseline is excluded and marked partial. Failed candidates are never ranked. Weights change display order only, never status or the Pareto front.

## BOM planning
Parts are grouped by MPN (else value + footprint); DNP and excluded parts are skipped. Only exact-MPN listings count. Per line: `cheapest` minimizes total price for the quantity (including buying up to a better break); `fastest` prefers stock now, else shortest stated lead time; `balanced` minimizes equal-weight normalized cost and lead time (lead = days/28 capped at 1, 1 if unstated). Unpriced lines are listed with reasons.

## Candidate hash
sha256 of canonical algorithm + version + changes, used to recognise identical candidates.
