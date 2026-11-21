"""Queryable projections of a parsed design revision.

The complete normalized design (tracks, pads, graphics...) lives as JSON in
object storage (a ``DesignFile`` of kind ``normalized``). These tables hold the
subsets the API needs to paginate, search and summarize without loading it.
All rows are owned by a revision and deleted with it.
"""

from __future__ import annotations

import uuid
from typing import Any

from sqlalchemy import Boolean, Float, ForeignKey, Index, Integer, String, UniqueConstraint, func
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from via_api.models.base import Base, UUIDPk


class _RevisionOwned(UUIDPk):
    revision_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("design_revisions.id", ondelete="CASCADE"), sort_order=-99
    )


class PCBLayer(_RevisionOwned, Base):
    __tablename__ = "pcb_layers"
    __table_args__ = (UniqueConstraint("revision_id", "name"),)

    ordinal: Mapped[int] = mapped_column(Integer)
    name: Mapped[str] = mapped_column(String(64))
    kind: Mapped[str] = mapped_column(String(32))
    side: Mapped[str] = mapped_column(String(16))
    source_type: Mapped[str | None] = mapped_column(String(32))
    user_name: Mapped[str | None] = mapped_column(String(64))


class PCBNet(_RevisionOwned, Base):
    __tablename__ = "pcb_nets"
    __table_args__ = (UniqueConstraint("revision_id", "name"),)

    code: Mapped[int] = mapped_column(Integer)
    name: Mapped[str] = mapped_column(String(255))
    pad_count: Mapped[int] = mapped_column(Integer, default=0)
    track_count: Mapped[int] = mapped_column(Integer, default=0)
    via_count: Mapped[int] = mapped_column(Integer, default=0)
    track_length: Mapped[float] = mapped_column(Float, default=0.0)


class PCBComponent(_RevisionOwned, Base):
    __tablename__ = "pcb_components"

    reference: Mapped[str] = mapped_column(String(64))
    value: Mapped[str | None] = mapped_column(String(255))
    footprint: Mapped[str] = mapped_column(String(255))
    layer: Mapped[str] = mapped_column(String(64))
    side: Mapped[str] = mapped_column(String(16))
    x: Mapped[float] = mapped_column(Float)
    y: Mapped[float] = mapped_column(Float)
    rotation: Mapped[float] = mapped_column(Float)
    pad_count: Mapped[int] = mapped_column(Integer, default=0)
    attributes: Mapped[list[str]] = mapped_column(JSONB, default=list)
    properties: Mapped[dict[str, Any]] = mapped_column(JSONB, default=dict)


class PCBGeometry(_RevisionOwned, Base):
    """Board-level geometry summary (one row per revision)."""

    __tablename__ = "pcb_geometry"
    __table_args__ = (UniqueConstraint("revision_id"),)

    outline_closed: Mapped[bool] = mapped_column(Boolean)
    min_x: Mapped[float | None] = mapped_column(Float)
    min_y: Mapped[float | None] = mapped_column(Float)
    max_x: Mapped[float | None] = mapped_column(Float)
    max_y: Mapped[float | None] = mapped_column(Float)
    width: Mapped[float | None] = mapped_column(Float)
    height: Mapped[float | None] = mapped_column(Float)
    area: Mapped[float | None] = mapped_column(Float)
    thickness: Mapped[float | None] = mapped_column(Float)
    copper_layer_count: Mapped[int] = mapped_column(Integer)
    normalized_file_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("design_files.id", ondelete="SET NULL"))


Index("ix_pcb_components_revision_reference", PCBComponent.revision_id, func.lower(PCBComponent.reference))
Index("ix_pcb_nets_revision_name", PCBNet.revision_id, func.lower(PCBNet.name))
