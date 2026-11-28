"""Weighted preference over a run's objectives. Display order only: weights never change validation,
status or the Pareto front, and failed candidates are never ranked.

Score of a candidate = sum(weight * relative change) / sum(weights), over the weighted objectives whose
metric is known before and after (all metrics are minimized, so lower is better). The relative change is
(after - before) / before when before > 0. When before is 0 the relative change is undefined, so that
metric is left out and the score is marked partial (a worsening from 0 still shows in the trade-offs and,
for new problems, fails validation).
"""

from __future__ import annotations

from collections.abc import Mapping

from via_opt.candidates import Candidate, Score, ValidationStatus
from via_opt.objectives import METRIC_FOR, Objective


def rank(candidates: list[Candidate], baseline: Mapping[str, float | None], weights: Mapping[Objective, float]) -> None:
    """Sets ``score`` on every rankable candidate (in place)."""
    active = {o: w for o, w in weights.items() if w > 0}
    if not active:
        return
    scored: list[Candidate] = []
    for c in candidates:
        if not c.metrics_after or c.validation.status == ValidationStatus.FAILED:
            continue
        total = used = 0.0
        excluded: list[str] = []
        for o, w in sorted(active.items(), key=lambda kv: kv[0].value):
            m = METRIC_FOR[o]
            b, a = baseline.get(m), c.metrics_after.get(m)
            if b is None or a is None:
                excluded.append(f"{m}: not measured")
            elif b <= 0:
                excluded.append(f"{m}: baseline is 0, relative change undefined")
            else:
                total += w * (a - b) / b
                used += w
        value = round(total / used, 6) if used else None
        c.score = Score(
            value=value, partial=bool(excluded), excluded=excluded, weights={o.value: w for o, w in active.items()}
        )
        scored.append(c)
    ranked = [(c.score.value, c.key, c) for c in scored if c.score is not None and c.score.value is not None]
    ordered = [c for _, _, c in sorted(ranked, key=lambda t: (t[0], t[1]))]
    for i, c in enumerate(ordered, start=1):
        assert c.score is not None
        c.score.rank = i
