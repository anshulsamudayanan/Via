"""Format adapters and the default registry."""

from __future__ import annotations

from pathlib import Path

from via_pcb.adapters.base import (
    AdapterNotFoundError,
    AdapterRegistry,
    PCBAdapter,
    UnsupportedFormatError,
)
from via_pcb.adapters.kicad import KiCadAdapter
from via_pcb.models import PCBDesign

SNIFF_BYTES = 4096

_registry: AdapterRegistry | None = None


def get_registry() -> AdapterRegistry:
    global _registry
    if _registry is None:
        _registry = AdapterRegistry()
        _registry.register(KiCadAdapter())
    return _registry


def detect_adapter(filename: str | None, head: bytes) -> PCBAdapter:
    return get_registry().detect(filename, head[:SNIFF_BYTES])


def parse_pcb(source: bytes | str | Path, filename: str | None = None) -> PCBDesign:
    """Detect the format of ``source`` and parse it.

    ``source`` may be raw bytes or a filesystem path.
    """
    if isinstance(source, (str, Path)):
        path = Path(source)
        data = path.read_bytes()
        filename = filename or path.name
    else:
        data = source
    adapter = detect_adapter(filename, data)
    return adapter.parse(data, filename=filename)


__all__ = [
    "AdapterNotFoundError",
    "AdapterRegistry",
    "KiCadAdapter",
    "PCBAdapter",
    "UnsupportedFormatError",
    "detect_adapter",
    "get_registry",
    "parse_pcb",
]
