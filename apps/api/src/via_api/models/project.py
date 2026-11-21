"""Projects and project-level membership."""

from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, Index, String, Text, UniqueConstraint, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from via_api.models.base import Base, CreatedAt, Timestamps, UUIDPk, str_enum
from via_api.models.enums import ProjectRole, ProjectVisibility


class Project(UUIDPk, Timestamps, Base):
    __tablename__ = "projects"

    organization_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("organizations.id", ondelete="RESTRICT"), index=True)
    owner_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id", ondelete="RESTRICT"), index=True)
    name: Mapped[str] = mapped_column(String(120))
    description: Mapped[str] = mapped_column(Text, default="", server_default="")
    visibility: Mapped[ProjectVisibility] = mapped_column(
        str_enum(ProjectVisibility, "project_visibility"),
        default=ProjectVisibility.PRIVATE,
        server_default=ProjectVisibility.PRIVATE.value,
    )
    archived_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    memberships: Mapped[list[ProjectMembership]] = relationship(back_populates="project", cascade="all, delete-orphan")


class ProjectMembership(UUIDPk, CreatedAt, Base):
    """Explicit project access. The project owner also has an ``owner`` row."""

    __tablename__ = "project_memberships"
    __table_args__ = (UniqueConstraint("project_id", "user_id"),)

    project_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("projects.id", ondelete="CASCADE"))
    user_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    role: Mapped[ProjectRole] = mapped_column(str_enum(ProjectRole, "project_role"))
    added_by_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"))

    project: Mapped[Project] = relationship(back_populates="memberships")


# Case-insensitive name search/sort within an organization.
Index("ix_projects_org_lower_name", Project.organization_id, func.lower(Project.name))
