"""Enumerations stored as VARCHAR + CHECK constraints."""

from enum import StrEnum


class OrganizationRole(StrEnum):
    OWNER = "owner"
    ADMIN = "admin"
    MEMBER = "member"


class ProjectRole(StrEnum):
    OWNER = "owner"
    EDITOR = "editor"
    VIEWER = "viewer"


class ProjectVisibility(StrEnum):
    #: Only the owner and explicit project members. The default.
    PRIVATE = "private"
    #: Additionally readable (viewer) by members of the owning organization.
    ORGANIZATION = "organization"


class RevisionStatus(StrEnum):
    PENDING = "pending"
    PROCESSING = "processing"
    READY = "ready"
    FAILED = "failed"


class DesignFileKind(StrEnum):
    SOURCE = "source"
    NORMALIZED = "normalized"


class UploadOutcome(StrEnum):
    ACCEPTED = "accepted"
    REJECTED = "rejected"
    DUPLICATE = "duplicate"


class AnalysisKind(StrEnum):
    PCB_IMPORT = "pcb_import"
    #: Stage 2: run the analysis checks on a parsed revision.
    PCB_ANALYSIS = "pcb_analysis"
    #: Stage 2: generate and validate optimization candidates.
    PCB_OPTIMIZATION = "pcb_optimization"
    #: Stage 2: patch the original file with a change set and import the result as a new revision.
    PCB_EXPORT = "pcb_export"


class ChangeSetStatus(StrEnum):
    DRAFT = "draft"
    APPLYING = "applying"
    APPLIED = "applied"
    FAILED = "failed"
    ROLLED_BACK = "rolled_back"


class ChangeStatus(StrEnum):
    PROPOSED = "proposed"
    APPLIED = "applied"
    REFUSED = "refused"


class FindingStatus(StrEnum):
    """User review state of a finding (separate from how the finding was verified)."""

    OPEN = "open"
    REVIEWED = "reviewed"
    DISMISSED = "dismissed"


class AnalysisStatus(StrEnum):
    QUEUED = "queued"
    RUNNING = "running"
    SUCCEEDED = "succeeded"
    FAILED = "failed"


class ConsentScope(StrEnum):
    #: Contribute derived, validated knowledge from a project to VIA Learn (future).
    VIA_LEARN_CONTRIBUTION = "via_learn_contribution"
    #: Allow sending project data to an external AI provider for a user-initiated operation (future).
    EXTERNAL_AI_PROCESSING = "external_ai_processing"
    #: Allow looking up the design's manufacturer part numbers with a supplier (Mouser) for prices and stock.
    SUPPLIER_LOOKUP = "supplier_lookup"
