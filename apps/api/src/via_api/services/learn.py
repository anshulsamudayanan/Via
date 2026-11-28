"""VIA Learn: contributions, review, withdrawal and search of the collective knowledge store.

The rules this module enforces (docs/VIA_LEARN.md):

* Nothing is contributed automatically. A contribution is a draft the contributor reviews, then submits.
* Project-derived drafts need the project owner's active ``via_learn_contribution`` consent and are
  de-identified first (``learn_scrub``). Free-text drafts are the contributor's own words.
* Nothing is searchable or reaches the AI until a reviewer approves it, and approval is not verification.
* A contributor can withdraw an entry at any time: its content is erased at once; the id, ownership and
  provenance rows stay so past AI outputs remain auditable.
* Retrieval reads only this store, never project data.
"""

from __future__ import annotations

import re
import uuid
from dataclasses import dataclass
from typing import Any

from sqlalchemy import func, literal_column, select, update
from sqlalchemy.orm import Session

from via_api.errors import APIError, not_found
from via_api.models import (
    AIOutput,
    AnalysisFinding,
    DataConsent,
    Design,
    DesignFile,
    DesignRevision,
    LearnEntry,
    LearnEntryVersion,
    PCBComponent,
    PCBNet,
    RecommendationRow,
)
from via_api.models.base import utcnow
from via_api.models.enums import (
    ConsentScope,
    LearnCategory,
    LearnOrigin,
    LearnStatus,
    LearnVerification,
    ProjectRole,
)
from via_api.services import access, activity, consent, learn_scrub
from via_api.services.activity import ClientInfo
from via_api.services.auth import AuthContext

DEFAULT_PERMISSIONS: dict[str, bool] = {"library_visible": True, "ai_retrieval": True}
#: How much each verification level counts when ranking search results (relevance is multiplied by it).
VERIFICATION_WEIGHT = {
    LearnVerification.VERIFIED: 1.0,
    LearnVerification.REVIEWED: 0.7,
    LearnVerification.UNVERIFIED: 0.4,
}
FINDING_CATEGORY_TO_LEARN = {
    "geometry": LearnCategory.PCB_DESIGN_PATTERN,
    "board_outline": LearnCategory.PCB_DESIGN_PATTERN,
    "design_rules": LearnCategory.MANUFACTURING_CONSTRAINT,
    "connectivity": LearnCategory.PCB_DESIGN_PATTERN,
    "routing": LearnCategory.ROUTING_PRACTICE,
    "placement": LearnCategory.PCB_DESIGN_PATTERN,
    "manufacturing": LearnCategory.MANUFACTURING_CONSTRAINT,
    "thermal": LearnCategory.THERMAL_DESIGN,
    "power": LearnCategory.THERMAL_DESIGN,
    "signal_integrity": LearnCategory.SIGNAL_INTEGRITY,
}

DRAFTED = "learn.draft_created"
SUBMITTED = "learn.submitted"
APPROVED = "learn.approved"
REJECTED = "learn.rejected"
WITHDRAWN = "learn.withdrawn"
VERIFICATION_SET = "learn.verification_set"
PERMISSIONS_SET = "learn.permissions_set"
CONSENT_GRANTED = "learn.consent_granted"
CONSENT_REVOKED = "learn.consent_revoked"


def _forbidden(message: str) -> APIError:
    return APIError(403, "forbidden", message)


def require_reviewer(ctx: AuthContext) -> None:
    if not ctx.user.learn_reviewer:
        raise _forbidden("Only VIA Learn reviewers can do that.")


# --- indexing and versions -------------------------------------------------------------------------------------


def _reindex(db: Session, entry: LearnEntry) -> None:
    """Rebuild the full-text vector (title weighted above description). Blank for anything not approved."""
    vector: Any
    if entry.status == LearnStatus.APPROVED:
        vector = func.setweight(func.to_tsvector("english", entry.title), literal_column("'A'")).op("||")(
            func.setweight(func.to_tsvector("english", entry.description), literal_column("'B'"))
        )
    else:
        vector = func.to_tsvector("english", "")
    db.execute(update(LearnEntry).where(LearnEntry.id == entry.id).values(search_vector=vector))


def _snapshot(db: Session, entry: LearnEntry, change: str, actor_id: uuid.UUID | None) -> None:
    db.add(
        LearnEntryVersion(
            entry_id=entry.id,
            version=entry.version,
            title=entry.title,
            description=entry.description,
            technical_metadata=entry.technical_metadata,
            verification_status=entry.verification_status,
            change=change,
            changed_by_id=actor_id,
        )
    )


# --- reading ---------------------------------------------------------------------------------------------------


def _is_mine(entry: LearnEntry, user_id: uuid.UUID) -> bool:
    return entry.contributor_id == user_id


def visible_to(ctx: AuthContext, entry: LearnEntry) -> bool:
    if _is_mine(entry, ctx.user.id):
        return True
    if entry.status == LearnStatus.DRAFT:
        return False
    if ctx.user.learn_reviewer:
        return True
    return entry.status == LearnStatus.APPROVED and bool(entry.permissions.get("library_visible", True))


def get_entry(db: Session, ctx: AuthContext, entry_id: uuid.UUID) -> LearnEntry:
    """An entry the caller may see; anything else is a 404 (existence of others' drafts isn't revealed)."""
    entry = db.get(LearnEntry, entry_id)
    if entry is None or not visible_to(ctx, entry):
        raise not_found("Knowledge entry")
    return entry


def _own(db: Session, ctx: AuthContext, entry_id: uuid.UUID) -> LearnEntry:
    entry = db.get(LearnEntry, entry_id)
    if entry is None or not _is_mine(entry, ctx.user.id):
        raise not_found("Contribution")
    return entry


def list_mine(
    db: Session, ctx: AuthContext, status: LearnStatus | None, limit: int, offset: int
) -> tuple[list[LearnEntry], int]:
    stmt = select(LearnEntry).where(LearnEntry.contributor_id == ctx.user.id)
    if status:
        stmt = stmt.where(LearnEntry.status == status)
    total = db.scalar(select(func.count()).select_from(stmt.subquery())) or 0
    return list(db.scalars(stmt.order_by(LearnEntry.created_at.desc()).limit(limit).offset(offset))), total


def review_queue(db: Session, ctx: AuthContext, limit: int, offset: int) -> tuple[list[LearnEntry], int]:
    require_reviewer(ctx)
    stmt = select(LearnEntry).where(LearnEntry.status == LearnStatus.PENDING_REVIEW)
    total = db.scalar(select(func.count()).select_from(stmt.subquery())) or 0
    return list(db.scalars(stmt.order_by(LearnEntry.submitted_at).limit(limit).offset(offset))), total


def versions(db: Session, ctx: AuthContext, entry_id: uuid.UUID) -> list[LearnEntryVersion]:
    entry = get_entry(db, ctx, entry_id)
    return list(
        db.scalars(
            select(LearnEntryVersion)
            .where(LearnEntryVersion.entry_id == entry.id)
            .order_by(LearnEntryVersion.created_at)
        )
    )


# --- creating drafts -------------------------------------------------------------------------------------------


def create_free_text(
    db: Session,
    ctx: AuthContext,
    *,
    category: LearnCategory,
    title: str,
    description: str,
    source: str,
    technical_metadata: dict[str, Any],
    client: ClientInfo,
) -> LearnEntry:
    entry = LearnEntry(
        contributor_id=ctx.user.id,
        origin=LearnOrigin.FREE_TEXT,
        status=LearnStatus.DRAFT,
        category=category,
        title=title.strip(),
        description=description.strip(),
        technical_metadata=technical_metadata,
        source=source.strip(),
        permissions=dict(DEFAULT_PERMISSIONS),
        provenance={"policy_version": consent.POLICY_VERSION, "author_declared_rights": True},
    )
    db.add(entry)
    db.flush()
    _snapshot(db, entry, "created", ctx.user.id)
    activity.record(
        db,
        DRAFTED,
        actor_id=ctx.user.id,
        client=client,
        target_type="learn_entry",
        target_id=entry.id,
        details={"origin": entry.origin.value, "category": entry.category.value},
    )
    return entry


def _design_identifiers(db: Session, design_id: uuid.UUID) -> tuple[set[str], set[str], set[str]]:
    """Reference designators, net names and names (design, project, file stems) of a design, all revisions."""
    revs = select(DesignRevision.id).where(DesignRevision.design_id == design_id)
    refs = set(db.scalars(select(PCBComponent.reference).where(PCBComponent.revision_id.in_(revs))))
    nets = set(db.scalars(select(PCBNet.name).where(PCBNet.revision_id.in_(revs))))
    design = db.get(Design, design_id)
    names: set[str] = set()
    if design is not None:
        names.add(design.name)
        from via_api.models import Project  # local import: avoids a cycle through models at import time

        project = db.get(Project, design.project_id)
        if project is not None:
            names.add(project.name)
    for filename in db.scalars(select(DesignFile.original_filename).where(DesignFile.revision_id.in_(revs))):
        names.add(re.sub(r"\.[A-Za-z0-9_]+$", "", filename or ""))
    return refs, {n for n in nets if n}, {n for n in names if n}


def create_from_recommendation(
    db: Session, ctx: AuthContext, recommendation_id: uuid.UUID, category: LearnCategory | None, client: ClientInfo
) -> LearnEntry:
    rec = db.get(RecommendationRow, recommendation_id)
    if rec is None:
        raise not_found("Recommendation")
    try:
        project, _ = access.get_project(
            db, ctx.user.id, rec.project_id, ProjectRole.OWNER, action="contribute to VIA Learn from"
        )
    except APIError as exc:
        if exc.status_code == 404:
            raise not_found("Recommendation") from exc
        raise
    grant = consent.active_consent(db, project.id, ConsentScope.VIA_LEARN_CONTRIBUTION)
    if grant is None:
        raise APIError(
            403,
            "consent_required",
            "Contributing from this project to VIA Learn needs the project owner's consent first.",
        )
    ai = db.get(AIOutput, rec.ai_output_id)
    cats = [
        c.value
        for c in db.scalars(
            select(AnalysisFinding.category).where(
                AnalysisFinding.id.in_([_uuid(i) for i in rec.evidence_finding_ids if _uuid(i)])
            )
        )
    ]
    refs, nets, names = _design_identifiers(db, rec.design_id)
    details = rec.details or {}

    def clean(text: str) -> tuple[str, learn_scrub.ScrubReport]:
        return learn_scrub.scrub_text(text, nets=nets, names=names)

    report = learn_scrub.ScrubReport()
    pieces: list[str] = []
    for label, text in (
        ("Problem", rec.problem),
        ("Proposed change", rec.proposed_change),
        ("Why it may help", rec.rationale),
    ):
        cleaned, r = clean(text)
        report.merge(r)
        pieces.append(f"{label}: {cleaned}")
    lists: dict[str, list[str]] = {}
    for key, label in (
        ("expected_benefits", "Expected benefits"),
        ("trade_offs", "Trade-offs"),
        ("required_validation", "How to validate"),
    ):
        cleaned_list = []
        for item in details.get(key, []):
            cleaned, r = clean(str(item))
            report.merge(r)
            cleaned_list.append(cleaned)
        lists[key] = cleaned_list
        if cleaned_list:
            pieces.append(f"{label}: " + "; ".join(cleaned_list))
    title, r = clean(rec.problem)
    report.merge(r)
    title = title.strip().split("\n")[0][:200]
    description = "\n\n".join(pieces)
    leftovers = learn_scrub.residual_identifiers(f"{title}\n{description}", refdes=refs, nets=nets, names=names)
    if leftovers:
        # Never store something that still names the design; the contributor can write free text instead.
        raise APIError(
            409, "scrub_incomplete", "This recommendation couldn't be fully de-identified, so it can't be contributed."
        )
    chosen = category or next(
        (FINDING_CATEGORY_TO_LEARN[c] for c in cats if c in FINDING_CATEGORY_TO_LEARN), LearnCategory.PCB_DESIGN_PATTERN
    )
    run_version = None
    if ai is not None and ai.analysis_run_id is not None:
        from via_api.models import AnalysisRun

        run = db.get(AnalysisRun, ai.analysis_run_id)
        run_version = run.analysis_version if run else None
    entry = LearnEntry(
        contributor_id=ctx.user.id,
        consent_id=grant.id,
        origin=LearnOrigin.PROJECT_DERIVED,
        status=LearnStatus.DRAFT,
        category=chosen,
        title=title,
        description=description,
        technical_metadata={
            "confidence": rec.confidence,
            "finding_categories": sorted(set(cats)),
            "required_validation": lists["required_validation"],
        },
        source="Derived from a VIA AI recommendation on the contributor's own project; identifiers removed.",
        permissions=dict(DEFAULT_PERMISSIONS),
        provenance={
            "policy_version": consent.POLICY_VERSION,
            "derived_from": "ai_recommendation",
            "ai_suggestion": True,
            "scrub": report.as_dict(),
            "model": ai.model if ai else None,
            "prompt_version": ai.prompt_version if ai else None,
            "engine_version": run_version,
        },
    )
    db.add(entry)
    db.flush()
    _snapshot(db, entry, "created", ctx.user.id)
    # Recorded in the *project's* audit log (private): which recommendation was drafted for contribution.
    activity.record(
        db,
        DRAFTED,
        actor_id=ctx.user.id,
        client=client,
        project_id=project.id,
        target_type="learn_entry",
        target_id=entry.id,
        details={"origin": entry.origin.value, "scrub": report.as_dict()},
    )
    return entry


def _uuid(value: str) -> uuid.UUID | None:
    try:
        return uuid.UUID(str(value))
    except ValueError:
        return None


# --- contributor actions ---------------------------------------------------------------------------------------


def submit(db: Session, ctx: AuthContext, entry_id: uuid.UUID, client: ClientInfo) -> LearnEntry:
    entry = _own(db, ctx, entry_id)
    if entry.status != LearnStatus.DRAFT:
        raise APIError(409, "not_draft", "Only a draft can be submitted for review.")
    if entry.origin == LearnOrigin.PROJECT_DERIVED:
        grant = db.get(DataConsent, entry.consent_id) if entry.consent_id else None
        if grant is None or grant.revoked_at is not None:
            raise APIError(
                403, "consent_required", "The project's VIA Learn consent was withdrawn, so this can't be submitted."
            )
    entry.status = LearnStatus.PENDING_REVIEW
    entry.submitted_at = utcnow()
    activity.record(db, SUBMITTED, actor_id=ctx.user.id, client=client, target_type="learn_entry", target_id=entry.id)
    return entry


def delete_draft(db: Session, ctx: AuthContext, entry_id: uuid.UUID) -> None:
    entry = _own(db, ctx, entry_id)
    if entry.status != LearnStatus.DRAFT:
        raise APIError(409, "not_draft", "Only a draft can be deleted. Withdraw a submitted contribution instead.")
    db.delete(entry)


def update_permissions(
    db: Session,
    ctx: AuthContext,
    entry_id: uuid.UUID,
    *,
    library_visible: bool | None,
    ai_retrieval: bool | None,
    client: ClientInfo,
) -> LearnEntry:
    entry = _own(db, ctx, entry_id)
    if entry.status == LearnStatus.WITHDRAWN:
        raise APIError(409, "withdrawn", "This contribution was withdrawn.")
    perms = dict(DEFAULT_PERMISSIONS) | dict(entry.permissions)
    if library_visible is not None:
        perms["library_visible"] = library_visible
    if ai_retrieval is not None:
        perms["ai_retrieval"] = ai_retrieval
    entry.permissions = perms
    activity.record(
        db,
        PERMISSIONS_SET,
        actor_id=ctx.user.id,
        client=client,
        target_type="learn_entry",
        target_id=entry.id,
        details=perms,
    )
    return entry


def _redact(db: Session, entry: LearnEntry, actor_id: uuid.UUID | None, client: ClientInfo | None) -> None:
    """Erase what the entry said. The row, ownership, consent link and provenance stay (audit)."""
    entry.status = LearnStatus.WITHDRAWN
    entry.withdrawn_at = utcnow()
    entry.title, entry.description, entry.source = "[withdrawn]", "", ""
    entry.technical_metadata = {}
    entry.verification_basis = None
    db.execute(
        update(LearnEntryVersion)
        .where(LearnEntryVersion.entry_id == entry.id)
        .values(title="[withdrawn]", description="", technical_metadata={})
    )
    _reindex(db, entry)
    activity.record(db, WITHDRAWN, actor_id=actor_id, client=client, target_type="learn_entry", target_id=entry.id)


def withdraw(db: Session, ctx: AuthContext, entry_id: uuid.UUID, client: ClientInfo) -> LearnEntry:
    """The contributor withdraws their entry; a reviewer may also take any entry down."""
    entry = db.get(LearnEntry, entry_id)
    if entry is None or not (_is_mine(entry, ctx.user.id) or (ctx.user.learn_reviewer and visible_to(ctx, entry))):
        raise not_found("Contribution")
    if entry.status != LearnStatus.WITHDRAWN:
        _redact(db, entry, ctx.user.id, client)
    return entry


def grant_learn_consent(db: Session, ctx: AuthContext, project_id: uuid.UUID, client: ClientInfo) -> DataConsent:
    project, _ = access.get_project(db, ctx.user.id, project_id, ProjectRole.OWNER, action="manage VIA Learn consent")
    return consent.grant(db, ctx, project.id, ConsentScope.VIA_LEARN_CONTRIBUTION, client)


def revoke_learn_consent(
    db: Session, ctx: AuthContext, project_id: uuid.UUID, client: ClientInfo, *, withdraw_existing: bool
) -> int:
    """Stop future contributions from the project and (by default) withdraw what it already contributed.
    Returns how many entries were withdrawn."""
    project, _ = access.get_project(db, ctx.user.id, project_id, ProjectRole.OWNER, action="manage VIA Learn consent")
    grants = list(
        db.scalars(
            select(DataConsent).where(
                DataConsent.project_id == project.id, DataConsent.scope == ConsentScope.VIA_LEARN_CONTRIBUTION
            )
        )
    )
    consent.revoke(db, ctx, project.id, ConsentScope.VIA_LEARN_CONTRIBUTION, client)
    count = 0
    if withdraw_existing and grants:
        entries = db.scalars(
            select(LearnEntry).where(
                LearnEntry.consent_id.in_([g.id for g in grants]), LearnEntry.status != LearnStatus.WITHDRAWN
            )
        )
        for entry in entries:
            _redact(db, entry, ctx.user.id, client)
            count += 1
    return count


# --- review ----------------------------------------------------------------------------------------------------


def review(
    db: Session,
    ctx: AuthContext,
    entry_id: uuid.UUID,
    *,
    approve: bool,
    note: str | None,
    verification: LearnVerification,
    basis: str | None,
    client: ClientInfo,
) -> LearnEntry:
    require_reviewer(ctx)
    entry = db.get(LearnEntry, entry_id)
    if entry is None or entry.status == LearnStatus.DRAFT:
        raise not_found("Contribution")
    if _is_mine(entry, ctx.user.id):
        raise _forbidden("You can't review your own contribution.")
    if entry.status != LearnStatus.PENDING_REVIEW:
        raise APIError(409, "not_pending", "Only a contribution waiting for review can be reviewed.")
    if approve:
        if verification != LearnVerification.UNVERIFIED and not (basis or "").strip():
            raise APIError(422, "basis_required", "Say what was checked when marking an entry reviewed or verified.")
        entry.status = LearnStatus.APPROVED
        entry.verification_status = verification
        entry.verification_basis = (basis or "").strip() or None
    else:
        if not (note or "").strip():
            raise APIError(422, "reason_required", "Say why the contribution is rejected.")
        entry.status = LearnStatus.REJECTED
    entry.reviewer_id, entry.reviewed_at, entry.review_note = ctx.user.id, utcnow(), (note or "").strip() or None
    if approve:
        _snapshot(db, entry, "approved", ctx.user.id)
    _reindex(db, entry)
    activity.record(
        db,
        APPROVED if approve else REJECTED,
        actor_id=ctx.user.id,
        client=client,
        target_type="learn_entry",
        target_id=entry.id,
        details={"verification": entry.verification_status.value},
    )
    return entry


def set_verification(
    db: Session,
    ctx: AuthContext,
    entry_id: uuid.UUID,
    *,
    verification: LearnVerification,
    basis: str | None,
    client: ClientInfo,
) -> LearnEntry:
    require_reviewer(ctx)
    entry = db.get(LearnEntry, entry_id)
    if entry is None or entry.status == LearnStatus.DRAFT:
        raise not_found("Knowledge entry")
    if entry.status != LearnStatus.APPROVED:
        raise APIError(409, "not_approved", "Only an approved entry has a verification status.")
    if verification != LearnVerification.UNVERIFIED and not (basis or "").strip():
        raise APIError(422, "basis_required", "Say what was checked when marking an entry reviewed or verified.")
    if verification == entry.verification_status and (basis or "").strip() == (entry.verification_basis or ""):
        return entry
    entry.verification_status = verification
    entry.verification_basis = (basis or "").strip() or None
    entry.version += 1
    _snapshot(db, entry, "verification_changed", ctx.user.id)
    activity.record(
        db,
        VERIFICATION_SET,
        actor_id=ctx.user.id,
        client=client,
        target_type="learn_entry",
        target_id=entry.id,
        details={"verification": verification.value, "version": entry.version},
    )
    return entry


# --- search ----------------------------------------------------------------------------------------------------


@dataclass(frozen=True)
class Hit:
    entry: LearnEntry
    score: float


_WORD = re.compile(r"[A-Za-z][A-Za-z0-9]{2,}")


def _tsquery_text(text: str) -> str | None:
    """OR of the distinctive words in ``text`` (letters and digits only, so nothing can inject tsquery syntax)."""
    words = list(dict.fromkeys(w.lower() for w in _WORD.findall(text)))[:16]
    return " | ".join(words) if words else None


def search(
    db: Session,
    text: str | None,
    *,
    category: LearnCategory | None = None,
    verification: LearnVerification | None = None,
    limit: int = 20,
    offset: int = 0,
    ai_only: bool = False,
) -> tuple[list[Hit], int]:
    """Approved entries matching ``text``, best first: relevance times the verification weight.

    ``ai_only`` also requires the contributor's ``ai_retrieval`` permission. With no text, newest first
    (still verified before unverified). This function has no project inputs and reads no project tables.
    """
    conds: list[Any] = [
        LearnEntry.status == LearnStatus.APPROVED,
        LearnEntry.permissions["ai_retrieval" if ai_only else "library_visible"].as_string().is_distinct_from("false"),
    ]
    if category:
        conds.append(LearnEntry.category == category)
    if verification:
        conds.append(LearnEntry.verification_status == verification)
    query = _tsquery_text(text or "")
    if text and text.strip() and query is None:
        return [], 0
    if query is not None:
        tsq = func.to_tsquery("english", query)
        rows = db.execute(
            select(LearnEntry, func.ts_rank_cd(LearnEntry.search_vector, tsq))
            .where(*conds, LearnEntry.search_vector.op("@@")(tsq))
            .limit(500)
        ).all()
        hits = [Hit(e, float(r) * VERIFICATION_WEIGHT[e.verification_status]) for e, r in rows]
    else:
        newest = db.scalars(select(LearnEntry).where(*conds).order_by(LearnEntry.created_at.desc()).limit(500))
        hits = [Hit(e, VERIFICATION_WEIGHT[e.verification_status]) for e in newest]
    hits.sort(key=lambda h: (-h.score, -h.entry.created_at.timestamp()))
    return hits[offset : offset + limit], len(hits)


def knowledge_used(db: Session, ai_output_ids: list[uuid.UUID]) -> dict[uuid.UUID, list[dict[str, Any]]]:
    """Library entries shown to the model for each AI output, with source attribution and whether it cited them.
    Reads the output's private retrieval log; entries since withdrawn show only their id and status."""
    from via_api.models import AIOutputKnowledge

    out: dict[uuid.UUID, list[dict[str, Any]]] = {i: [] for i in ai_output_ids}
    if not ai_output_ids:
        return out
    rows = db.execute(
        select(AIOutputKnowledge, LearnEntry)
        .join(LearnEntry, LearnEntry.id == AIOutputKnowledge.entry_id)
        .where(AIOutputKnowledge.ai_output_id.in_(ai_output_ids))
        .order_by(AIOutputKnowledge.rank)
    ).all()
    for link, entry in rows:
        out[link.ai_output_id].append(
            {
                "entry_id": entry.id,
                "version": link.entry_version,
                "title": entry.title,
                "category": entry.category.value,
                "verification_status": entry.verification_status.value,
                "source": entry.source,
                "status": entry.status.value,
                "cited": link.cited,
            }
        )
    return out
