# ruff: noqa: E501
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
        "Re-place parts to shorten connections (descent + seeded simulated annealing, with rotation)",
        ["placement", "routing"],
        "partial",
        understands=PLACEMENT_UNDERSTANDS,
        cannot_evaluate=CANNOT_EVALUATE,
        preserves=PRESERVED,
        limitations=[
            "Shortens the unrouted connection length (ratsnest), which is not the same as routability or congestion.",
            "Moved parts that carry routed nets must be re-routed in KiCad before connectivity can be verified.",
            "A part is moved or rotated in one candidate, not both; bottom-side parts are not rotated.",
            "Nets with more than 40 pads (power, ground) are ignored while searching; the reported ratsnest includes them.",
            "No grouping, thermal spacing or signal-aware placement.",
        ],
    ),
    _m(
        "placement_compaction",
        "Re-place parts, then fit the outline to the result",
        ["area", "placement", "cost"],
        "partial",
        understands=[*PLACEMENT_UNDERSTANDS, "outline_fixed"],
        cannot_evaluate=CANNOT_EVALUATE,
        preserves=PRESERVED,
        limitations=[
            "Placement is optimised for connection length, not for area: offered only when the outline then fits smaller than the plain fit.",
            "Needs re-routing; check the enclosure and mounting before applying.",
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
    _m(
        "area_analysis",
        "Board area analysis (utilisation, unused margins, largest empty rectangle, density)",
        ["area"],
        "implemented",
        preserves=PRESERVED,
        limitations=[
            "Occupancy uses part extents (courtyard when present) on a grid; the largest empty rectangle needs a rectangular outline."
        ],
    ),
    _m(
        "margin_analysis",
        "Manufacturing rule margins: violations and potential risks per rule",
        ["manufacturability"],
        "implemented",
        requires=["a manufacturing profile"],
        preserves=PRESERVED,
        limitations=["Risk bands are a VIA heuristic; compliance needs your fabricator's rules as a project profile."],
    ),
    _m(
        "bom_cost",
        "BOM cost from live Mouser listings (cheapest, fastest, balanced)",
        ["cost"],
        "partial",
        requires=[
            "a build quantity",
            "MOUSER_API_KEY on the server",
            "the project owner's supplier consent",
            "manufacturer part numbers on the footprints",
        ],
        preserves=PRESERVED,
        limitations=[
            "One supplier (Mouser): the strategies differ by listing, order quantity and stock, not by competing distributors.",
            "Only listings with exactly the same manufacturer part number are used; no substitutes are suggested.",
            "Lines without a part number or a listing are left out of the totals and listed.",
            "Prices are the supplier's listing at the time of the run, not a quote.",
        ],
    ),
    _m(
        "component_alternates",
        "Alternative components checked for electrical and physical compatibility",
        ["cost"],
        "planned",
        requires=["parametric component data", "engineer approval of each substitution"],
    ),
    _m("rerouting", "Re-routing and autorouting", ["routing"], "unsupported"),
    _m("signal_integrity", "Impedance, length matching and signal-integrity optimization", ["routing"], "unsupported"),
    _m("thermal_simulation", "Thermal simulation", ["thermal"], "unsupported"),
]

_BY_KEY = {m.key: m for m in MODULES}


def spec_for(key: str) -> ModuleSpec | None:
    return _BY_KEY.get(key)
