"""VIA PCB engine.

Converts vendor PCB files into VIA's normalized, tool-agnostic board model.

Typical use::

    from via_pcb import parse_pcb

    board = parse_pcb(path_or_bytes, filename="board.kicad_pcb")
    print(board.stats.component_count)
"""

from via_pcb.adapters import (
    AdapterNotFoundError,
    PCBAdapter,
    UnsupportedFormatError,
    detect_adapter,
    get_registry,
    parse_pcb,
)
from via_pcb.models import ENGINE_VERSION, SCHEMA_VERSION, PCBDesign
from via_pcb.project import (
    ARCHIVE_EXTENSIONS,
    ArchiveLimits,
    ProjectArchiveError,
    ProjectPlan,
    inspect_project,
    is_project_archive,
    parse_project,
    read_project,
)

__all__ = [
    "ARCHIVE_EXTENSIONS",
    "ENGINE_VERSION",
    "SCHEMA_VERSION",
    "AdapterNotFoundError",
    "ArchiveLimits",
    "PCBAdapter",
    "PCBDesign",
    "ProjectArchiveError",
    "ProjectPlan",
    "UnsupportedFormatError",
    "detect_adapter",
    "get_registry",
    "inspect_project",
    "is_project_archive",
    "parse_pcb",
    "parse_project",
    "read_project",
]
