"""SQLAlchemy models. Importing this package registers every table on ``Base.metadata``."""

from via_api.models.activity import ActivityLog, AnalysisRun, DataConsent
from via_api.models.base import Base
from via_api.models.design import Design, DesignFile, DesignRevision, UploadRecord
from via_api.models.identity import (
    Organization,
    OrganizationMembership,
    PasswordResetToken,
    User,
    UserSession,
)
from via_api.models.pcb import PCBComponent, PCBGeometry, PCBLayer, PCBNet
from via_api.models.project import Project, ProjectMembership

__all__ = [
    "ActivityLog",
    "AnalysisRun",
    "Base",
    "DataConsent",
    "Design",
    "DesignFile",
    "DesignRevision",
    "Organization",
    "OrganizationMembership",
    "PCBComponent",
    "PCBGeometry",
    "PCBLayer",
    "PCBNet",
    "PasswordResetToken",
    "Project",
    "ProjectMembership",
    "UploadRecord",
    "User",
    "UserSession",
]
