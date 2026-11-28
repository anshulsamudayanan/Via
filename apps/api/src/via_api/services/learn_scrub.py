"""De-identification for project-derived VIA Learn contributions.

Deterministic, no AI: before a contribution leaves a project it is rewritten so that nothing that names
*this* design survives: reference designators, net names, project and design names, ids. What remains is the
engineering statement. The contributor still reviews the exact result before submitting it.

Generic power and ground names (``GND``, ``VCC``, ``3V3`` ...) are kept: they identify nothing and the advice
is unreadable without them. Numbers are kept (they are the engineering content), so the preview matters.
"""

from __future__ import annotations

import re
from collections.abc import Iterable
from dataclasses import dataclass, field

GENERIC_NETS = frozenset(
    {"GND", "AGND", "DGND", "PGND", "VCC", "VDD", "VSS", "VEE", "VBUS", "VIN", "VOUT", "VBAT", "+3V3", "3V3", "+3.3V",
     "+5V", "5V", "+12V", "12V", "+1V8", "1V8", "+24V", "24V"}
)  # fmt: skip

#: Any reference-designator-looking token, whether or not it is in this design.
_REFDES = re.compile(r"\b(?:R|C|L|U|J|P|Q|D|Y|X|K|F|T|SW|TP|FB|IC|CN|LED|BT|RV|JP|H|M)\d{1,4}[A-Z]?\b")
_UUID = re.compile(r"\b[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}\b")
_FILENAME = re.compile(r"\b[\w\-.]+\.(?:kicad_pcb|kicad_pro|kicad_sch|zip)\b", re.IGNORECASE)


@dataclass
class ScrubReport:
    parts: int = 0
    nets: int = 0
    names: int = 0
    ids: int = 0
    notes: list[str] = field(default_factory=list)

    def merge(self, other: ScrubReport) -> None:
        self.parts += other.parts
        self.nets += other.nets
        self.names += other.names
        self.ids += other.ids

    def as_dict(self) -> dict[str, int]:
        return {"parts": self.parts, "nets": self.nets, "names": self.names, "ids": self.ids}


def _word(term: str) -> re.Pattern[str]:
    # Not preceded or followed by a name character, so "R1" never matches inside "R10" or "NETR1".
    return re.compile(rf"(?<![\w+.\-]){re.escape(term)}(?![\w])")


def scrub_text(text: str, *, nets: Iterable[str], names: Iterable[str]) -> tuple[str, ScrubReport]:
    """Return ``text`` with identifying terms replaced, and how many of each kind were replaced."""
    report = ScrubReport()
    out = text

    def swap(pattern: re.Pattern[str], repl: str, attr: str) -> None:
        nonlocal out
        out, n = pattern.subn(repl, out)
        setattr(report, attr, getattr(report, attr) + n)

    swap(_FILENAME, "<file>", "names")
    swap(_UUID, "<id>", "ids")
    for name in sorted({n.strip() for n in names if n and len(n.strip()) >= 3}, key=len, reverse=True):
        swap(re.compile(re.escape(name), re.IGNORECASE), "<project>", "names")
    for net in sorted({n for n in nets if n and n.upper() not in GENERIC_NETS}, key=len, reverse=True):
        swap(_word(net), "<net>", "nets")
    swap(_REFDES, "<part>", "parts")
    return out, report


def residual_identifiers(text: str, *, refdes: Iterable[str], nets: Iterable[str], names: Iterable[str]) -> list[str]:
    """Identifying terms of this design still present in ``text`` (should be empty after scrubbing)."""
    found = [r for r in refdes if _word(r).search(text)]
    found += [n for n in nets if n.upper() not in GENERIC_NETS and _word(n).search(text)]
    found += [n.strip() for n in names if len(n.strip()) >= 3 and n.strip().lower() in text.lower()]
    return sorted(set(found))
