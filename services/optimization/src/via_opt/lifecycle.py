"""A candidate's lifecycle, derived from its stored status and validation. The stored status strings are
unchanged (the decision route and clients compare them); this adds the engineer-facing view.

``generated`` and ``evaluating`` belong to the run (queued, running): candidates are only stored once they
have been evaluated and validated.
"""

from __future__ import annotations

LIFECYCLES = ("validated", "validation_failed", "needs_review", "accepted", "applied", "rejected")


def lifecycle(status: str, validation_status: str, status_reason: str | None = None, applied: bool = False) -> str:
    if applied:
        return "applied"
    if status == "accepted":
        return "accepted"
    if status == "rejected":
        # The engine rejects failed candidates without a reason; a person always gives one.
        return "validation_failed" if validation_status == "failed" and not status_reason else "rejected"
    if status == "validated":
        return "validated"
    return "needs_review"
