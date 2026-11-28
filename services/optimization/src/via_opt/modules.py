"""What each optimization module understands, requires, can't evaluate and preserves, and how complete it is.

Served read-only at ``GET /optimization-modules``. ``status`` is one of implemented, partial, planned or
unsupported. Planned and unsupported entries are listed so nothing is implied to work that doesn't.
"""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

#: Requirement kinds an engineer may declare that VIA can record but not evaluate (reported as unverified).
CANNOT_EVALUATE = [
    "impedance_targets",
    "length_matching",
    "differential_pair_skew",
    "signal_integrity",
    "thermal_simulation",
    "emc",
    "enclosure_fit",
    "creepage_and_voltage_clearance",
]
PRESERVED = ["component_identity", "net_connectivity"]
PLACEMENT_UNDERSTANDS = [
    "fixed_components",
    "within_outline",
    "edge_margin",
    "component_overlap",
    "keepout_zones",
    "board_size",
]


class ModuleSpec(BaseModel):
    model_config = ConfigDict(extra="forbid")

    key: str
    title: str
    objectives: list[str]
    status: Literal["implemented", "partial", "planned", "unsupported"]
    understands: list[str] = Field(default_factory=list)
    requires: list[str] = Field(default_factory=list)
    cannot_evaluate: list[str] = Field(default_factory=list)
    preserves: list[str] = Field(default_factory=list)
    limitations: list[str] = Field(default_factory=list)


def _m(key: str, title: str, objectives: list[str], status: str, **kw: list[str]) -> ModuleSpec:
    return ModuleSpec(key=key, title=title, objectives=objectives, status=status, **kw)  # type: ignore[arg-type]


MODULES: list[ModuleSpec] = [
    _m(
        "outline_fit",
        "Fit the board outline to its content",
        ["area", "cost"],
        "implemented",
        understands=["outline_fixed", "board_size", "edge_margin", "within_outline"],
        requires=["a rectangular outline"],
        cannot_evaluate=CANNOT_EVALUATE,
        preserves=PRESERVED,
        limitations=[
            "Only rectangular outlines are resized.",
            "Doesn't know the enclosure or mounting: check them before applying.",
        ],
    ),
    _m(
        "via_standardization",
        "Bring vias up to the manufacturing profile",
        ["manufacturability", "cost"],
        "implemented",
        understands=["profile_minimums", "board_size"],
        requires=["a manufacturing profile"],
        cannot_evaluate=CANNOT_EVALUATE,
        preserves=PRESERVED,
        limitations=["Vias that can't grow without breaking clearance are reported and left alone."],
    ),
    _m(
        "track_min_width",
        "Widen tracks below the profile minimum",
        ["manufacturability", "cost"],
        "implemented",
        understands=["profile_minimums"],
        requires=["a manufacturing profile"],
        cannot_evaluate=CANNOT_EVALUATE,
        preserves=PRESERVED,
    ),
    _m(
        "power_track_widening",
        "Widen power tracks for their current (IPC-2221)",
        ["thermal"],
        "partial",
        understands=["profile_minimums"],
        requires=["options.power: current per net", "copper thickness"],
        cannot_evaluate=CANNOT_EVALUATE,
        preserves=PRESERVED,
        limitations=[
            "Track width for a given current only: no temperature rise simulation, no copper pours or via current."
        ],
    ),
    _m(
        "placement_ratsnest",
        "Move parts closer to what they connect to",
        ["placement", "routing"],
        "partial",
        understands=PLACEMENT_UNDERSTANDS,
        cannot_evaluate=CANNOT_EVALUATE,
        preserves=PRESERVED,
        limitations=[
            "Shortens the unrouted connection length (ratsnest), which is not the same as routability.",
            "Moved parts that carry routed nets must be re-routed in KiCad before connectivity can be verified.",
            "No rotation, density or grouping yet.",
        ],
    ),
    _m(
        "layer_reduction",
        "Propose fewer copper layers",
        ["layers", "cost"],
        "partial",
        cannot_evaluate=CANNOT_EVALUATE,
        preserves=[],
        limitations=["A proposal only: the stackup change and any re-routing are made in KiCad."],
    ),
    _m("area_analysis", "Board area analysis (utilisation, empty regions)", ["area"], "planned"),
    _m(
        "placement_annealing", "Seeded simulated-annealing placement with rotation", ["placement", "routing"], "planned"
    ),
    _m("margin_analysis", "Manufacturing rule margins and risk classes", ["manufacturability"], "planned"),
    _m(
        "bom_cost",
        "BOM cost from live supplier data (cheapest, fastest, balanced)",
        ["cost"],
        "planned",
        requires=["supplier data", "build quantity", "consent to look up part numbers"],
    ),
    _m("rerouting", "Re-routing and autorouting", ["routing"], "unsupported"),
    _m("signal_integrity", "Impedance, length matching and signal-integrity optimization", ["routing"], "unsupported"),
    _m("thermal_simulation", "Thermal simulation", ["thermal"], "unsupported"),
]

_BY_KEY = {m.key: m for m in MODULES}


def spec_for(key: str) -> ModuleSpec | None:
    return _BY_KEY.get(key)
