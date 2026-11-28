"""VIA Learn: private recommendation feedback and the separate collective knowledge store.

Two sides, kept apart on purpose (docs/DATABASE.md "VIA Learn readiness", docs/VIA_LEARN.md):

* **Private side**: ``recommendation_feedback`` and ``ai_output_knowledge`` belong to a project and follow
  project access rules.
* **Learn store**: ``learn_entries`` and ``learn_entry_versions`` hold only contributed, de-identified
  knowledge. They have **no foreign keys to projects, designs, revisions or files**; provenance is the
  contributor, the consent record and an opaque id.
"""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any

from sqlalchemy import Boolean, DateTime, Float, ForeignKey, Index, Integer, String, Text, text
from sqlalchemy.dialects.postgresql import JSONB, TSVECTOR
from sqlalchemy.orm import Mapped, mapped_column

from via_api.models.base import Base, CreatedAt, Timestamps, UUIDPk, str_enum
from via_api.models.enums import FeedbackType, LearnCategory, LearnOrigin, LearnStatus, LearnVerification


class RecommendationFeedback(UUIDPk, CreatedAt, Base):
    """A user's feedback on one recommendation (private to the project). Rows are never edited: a later
    opinion is a new row, and evaluation uses the latest opinion per user."""

    __tablename__ = "recommendation_feedback"

    recommendation_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("recommendations.id", ondelete="CASCADE"))
    project_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("projects.id", ondelete="CASCADE"), index=True)
    design_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("designs.id", ondelete="CASCADE"))
    analysis_run_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("analysis_runs.id", ondelete="SET NULL"))
    user_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    #: Finding category of the recommendation's first evidence finding, or "uncategorised".
    category: Mapped[str] = mapped_column(String(32))
    feedback_type: Mapped[FeedbackType] = mapped_column(str_enum(FeedbackType, "feedback_type"))
    #: The reason for a rejection, a correction, the incorrect assumption or a free comment.
    explanation: Mapped[str | None] = mapped_column(Text)
    # Versions in force when the recommendation was made (from the AI output and its analysis run).
    model: Mapped[str] = mapped_column(String(128))
    prompt_version: Mapped[str] = mapped_column(String(32))
    engine_version: Mapped[str | None] = mapped_column(String(32))


class LearnEntry(UUIDPk, Timestamps, Base):
    """One contribution to the knowledge library, from draft to (maybe) approved. No link to any project."""

    __tablename__ = "learn_entries"

    #: Nullable so deleting an account never deletes shared knowledge; the entry keeps its provenance.
    contributor_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"), index=True)
    #: The consent that authorised a project-derived contribution (null for free text).
    consent_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("data_consents.id", ondelete="SET NULL"))
    origin: Mapped[LearnOrigin] = mapped_column(str_enum(LearnOrigin, "learn_origin"))
    status: Mapped[LearnStatus] = mapped_column(str_enum(LearnStatus, "learn_status"))
    category: Mapped[LearnCategory] = mapped_column(str_enum(LearnCategory, "learn_category"))
    title: Mapped[str] = mapped_column(String(200))
    description: Mapped[str] = mapped_column(Text)
    #: Structured technical detail (applies_to, conditions, numbers with units, tags); no identifiers.
    technical_metadata: Mapped[dict[str, Any]] = mapped_column(JSONB, default=dict, server_default="{}")
    #: Where the knowledge comes from, in the contributor's words.
    source: Mapped[str] = mapped_column(Text)
    #: How it was produced: policy version, scrub summary, versions of the engine and model that made it.
    provenance: Mapped[dict[str, Any]] = mapped_column(JSONB, default=dict, server_default="{}")
    verification_status: Mapped[LearnVerification] = mapped_column(
        str_enum(LearnVerification, "learn_verification"),
        default=LearnVerification.UNVERIFIED,
        server_default=LearnVerification.UNVERIFIED.value,
    )
    #: What a reviewer checked or cited when marking an entry reviewed or verified.
    verification_basis: Mapped[str | None] = mapped_column(Text)
    #: {"library_visible": bool, "ai_retrieval": bool}, managed by the contributor.
    permissions: Mapped[dict[str, Any]] = mapped_column(JSONB, default=dict, server_default="{}")
    version: Mapped[int] = mapped_column(Integer, default=1, server_default="1")
    submitted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    reviewer_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"))
    reviewed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    review_note: Mapped[str | None] = mapped_column(Text)
    withdrawn_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    #: Full-text index of title and description (maintained by the service, blank once withdrawn).
    search_vector: Mapped[Any] = mapped_column(TSVECTOR, server_default=text("''::tsvector"))


class LearnEntryVersion(UUIDPk, CreatedAt, Base):
    """What an entry said at each version (audit). Content is blanked when the entry is withdrawn."""

    __tablename__ = "learn_entry_versions"

    entry_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("learn_entries.id", ondelete="CASCADE"), index=True)
    version: Mapped[int] = mapped_column(Integer)
    title: Mapped[str] = mapped_column(String(200))
    description: Mapped[str] = mapped_column(Text)
    technical_metadata: Mapped[dict[str, Any]] = mapped_column(JSONB, default=dict, server_default="{}")
    verification_status: Mapped[LearnVerification] = mapped_column(str_enum(LearnVerification, "learn_verification"))
    #: created | approved | verification_changed | withdrawn
    change: Mapped[str] = mapped_column(String(32))
    changed_by_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"))


class AIOutputKnowledge(CreatedAt, Base):
    """Which knowledge entries were put in front of the model for one AI output, and which it cited.
    Only a citation shows an entry influenced the answer. Private to the project of the AI output."""

    __tablename__ = "ai_output_knowledge"

    ai_output_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("ai_outputs.id", ondelete="CASCADE"), primary_key=True)
    entry_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("learn_entries.id", ondelete="CASCADE"), primary_key=True)
    entry_version: Mapped[int] = mapped_column(Integer)
    rank: Mapped[int] = mapped_column(Integer)
    score: Mapped[float] = mapped_column(Float)
    cited: Mapped[bool] = mapped_column(Boolean, default=False, server_default="false")


Index(
    "ix_recommendation_feedback_rec_created",
    RecommendationFeedback.recommendation_id,
    RecommendationFeedback.created_at,
)
Index("ix_learn_entries_status_category", LearnEntry.status, LearnEntry.category)
Index("ix_learn_entries_search", LearnEntry.search_vector, postgresql_using="gin")
