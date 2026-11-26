"""Pareto comparison of candidates over the requested objectives (all metrics minimized)."""

from __future__ import annotations

from collections.abc import Mapping, Sequence


def dominates(a: Mapping[str, float | None], b: Mapping[str, float | None], keys: Sequence[str]) -> bool:
    """``a`` is no worse than ``b`` on every key and strictly better on at least one (missing = not comparable)."""
    better = False
    for k in keys:
        va, vb = a.get(k), b.get(k)
        if va is None or vb is None:
            return False
        if va > vb + 1e-9:
            return False
        if va < vb - 1e-9:
            better = True
    return better


def pareto_front(points: Mapping[str, Mapping[str, float | None]], keys: Sequence[str]) -> list[str]:
    """Ids of points no other point dominates."""
    return [i for i, p in points.items() if not any(dominates(q, p, keys) for j, q in points.items() if j != i)]
