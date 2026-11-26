"""Manufacturing profiles: the fabrication capabilities a design is checked against.

VIA does not know any particular manufacturer's capabilities. The built-in profiles are VIA
defaults (common, deliberately round numbers), not a manufacturer's specification, and every
finding says which profile and values it used. Users define their own profiles per project
(stored by the API); each analysis run records the exact values it used.
"""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field


class ManufacturingProfile(BaseModel):
    model_config = ConfigDict(extra="forbid")

    key: str = Field(description="Built-in key (via-*) or the stored profile's id")
    name: str
    description: str = ""
    source: str = Field(description="Where the values come from, shown with findings")
    min_track_width: float = Field(ge=0, le=100)
    min_clearance: float = Field(ge=0, le=100, description="Copper to copper, different nets")
    min_drill: float = Field(ge=0, le=100, description="Smallest finished hole")
    min_via_diameter: float = Field(ge=0, le=100)
    min_annular_ring: float = Field(ge=0, le=100, description="(pad or via size - drill) / 2")
    min_hole_to_hole: float = Field(ge=0, le=100, description="Hole edge to hole edge")
    min_copper_to_edge: float = Field(ge=0, le=100, description="Copper to board edge")
    min_silk_width: float = Field(ge=0, le=100, description="Silkscreen line width")


_VIA_SOURCE = "VIA default profile: typical values, not any manufacturer's specification. Confirm with your fabricator."

BUILTIN: dict[str, ManufacturingProfile] = {
    p.key: p
    for p in (
        ManufacturingProfile(
            key="via-conservative",
            name="VIA conservative",
            description="Widely available capabilities; the default.",
            source=_VIA_SOURCE,
            min_track_width=0.15,
            min_clearance=0.15,
            min_drill=0.3,
            min_via_diameter=0.6,
            min_annular_ring=0.15,
            min_hole_to_hole=0.5,
            min_copper_to_edge=0.3,
            min_silk_width=0.15,
        ),
        ManufacturingProfile(
            key="via-advanced",
            name="VIA advanced",
            description="Tighter capabilities offered by many fabricators, often at extra cost.",
            source=_VIA_SOURCE,
            min_track_width=0.1,
            min_clearance=0.1,
            min_drill=0.2,
            min_via_diameter=0.45,
            min_annular_ring=0.1,
            min_hole_to_hole=0.25,
            min_copper_to_edge=0.2,
            min_silk_width=0.1,
        ),
    )
}
DEFAULT_PROFILE = "via-conservative"
