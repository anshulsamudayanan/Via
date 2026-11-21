"""Adapter contract and registry.

An adapter turns one vendor format into a :class:`~via_pcb.models.PCBDesign`.
Adding a format (Altium, Eagle, ODB++, IPC-2581...) means writing one class
that implements :class:`PCBAdapter` and registering it; nothing else in VIA
needs to change.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from pathlib import Path
from typing import ClassVar

from via_pcb.models import PCBDesign


class UnsupportedFormatError(ValueError):
    """The file was recognised but cannot be converted (corrupt, unsupported version...)."""


class AdapterNotFoundError(UnsupportedFormatError):
    """No registered adapter recognises the file."""


class PCBAdapter(ABC):
    #: Stable identifier stored with every parsed design, e.g. ``"kicad"``.
    format_id: ClassVar[str]
    #: Human-readable name.
    display_name: ClassVar[str]
    #: Lower-case file extensions, including the dot.
    extensions: ClassVar[tuple[str, ...]]

    @abstractmethod
    def sniff(self, head: bytes) -> bool:
        """Return True if the first bytes of a file look like this format."""

    @abstractmethod
    def parse(self, data: bytes, filename: str | None = None) -> PCBDesign:
        """Convert raw file bytes into the normalized model.

        Must raise :class:`UnsupportedFormatError` for invalid input and must
        never execute or import anything from the file.
        """

    def matches(self, filename: str | None, head: bytes) -> bool:
        ext_ok = filename is None or Path(filename).suffix.lower() in self.extensions
        return ext_ok and self.sniff(head)


class AdapterRegistry:
    def __init__(self) -> None:
        self._adapters: dict[str, PCBAdapter] = {}

    def register(self, adapter: PCBAdapter) -> None:
        if adapter.format_id in self._adapters:
            raise ValueError(f"Adapter '{adapter.format_id}' already registered")
        self._adapters[adapter.format_id] = adapter

    def get(self, format_id: str) -> PCBAdapter:
        try:
            return self._adapters[format_id]
        except KeyError as exc:
            raise AdapterNotFoundError(f"Unknown format '{format_id}'") from exc

    def all(self) -> list[PCBAdapter]:
        return list(self._adapters.values())

    @property
    def extensions(self) -> set[str]:
        return {ext for a in self._adapters.values() for ext in a.extensions}

    def detect(self, filename: str | None, head: bytes) -> PCBAdapter:
        for adapter in self._adapters.values():
            if adapter.matches(filename, head):
                return adapter
        supported = ", ".join(sorted(self.extensions)) or "none"
        raise AdapterNotFoundError(f"Unrecognised PCB file. Supported formats: {supported}")
