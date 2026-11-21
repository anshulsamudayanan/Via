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

__all__ = [
    "ENGINE_VERSION",
    "SCHEMA_VERSION",
    "AdapterNotFoundError",
    "PCBAdapter",
    "PCBDesign",
    "UnsupportedFormatError",
    "detect_adapter",
    "get_registry",
    "parse_pcb",
]
