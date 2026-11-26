"""VIA's normalized, tool-agnostic PCB representation.

Every format adapter produces a :class:`PCBDesign`. Everything downstream (the
API, the web viewer, future VIA Intelligence / Optimize analyses) consumes only
this model, never vendor formats.

Conventions
-----------
* Units: millimetres for lengths, mm² for areas, degrees for angles.
* Coordinates: board space, origin and axis direction as in the source tool
  (KiCad: +X right, +Y down). ``source.y_axis`` records the direction so
  consumers can flip if needed.
* All positions are *absolute* (footprint-local coordinates are resolved by the
  adapter).
* Object identity (schema 1.1+): components, pads, tracks, vias and zones carry
  ``uuid`` (exactly as in the source, ``None`` when the source has none) and ``id``
  (a stable reference within the design: the source UUID when present, otherwise
  derived deterministically from the object's content, so re-parsing the same file
  gives the same ids). Designs stored with schema 1.0 have ``id = None``.
* ``SCHEMA_VERSION`` follows semver: bump the minor version for additive changes
  and the major version for breaking ones. Persisted designs carry the version
  they were produced with.
"""

from __future__ import annotations

from enum import StrEnum

from pydantic import BaseModel, ConfigDict, Field

SCHEMA_VERSION = "1.1.0"
ENGINE_VERSION = "0.2.0"


class _Model(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=False)


class Point(_Model):
    x: float
    y: float


class BoundingBox(_Model):
    min_x: float
    min_y: float
    max_x: float
    max_y: float

    @property
    def width(self) -> float:
        return self.max_x - self.min_x

    @property
    def height(self) -> float:
        return self.max_y - self.min_y


class LayerKind(StrEnum):
    COPPER = "copper"
    SILKSCREEN = "silkscreen"
    SOLDER_MASK = "solder_mask"
    SOLDER_PASTE = "solder_paste"
    ADHESIVE = "adhesive"
    FABRICATION = "fabrication"
    COURTYARD = "courtyard"
    EDGE = "edge"
    MARGIN = "margin"
    DOCUMENTATION = "documentation"
    USER = "user"


class Side(StrEnum):
    TOP = "top"
    BOTTOM = "bottom"
    INNER = "inner"
    NONE = "none"


class Layer(_Model):
    index: int = Field(description="Ordinal in the source file")
    name: str = Field(description="Canonical name, e.g. 'F.Cu'")
    kind: LayerKind
    side: Side
    source_type: str | None = Field(default=None, description="Raw type in the source, e.g. 'signal'")
    user_name: str | None = None


class Net(_Model):
    code: int
    name: str


class PadType(StrEnum):
    SMD = "smd"
    THROUGH_HOLE = "through_hole"
    NPTH = "npth"
    CONNECT = "connect"


class Drill(_Model):
    diameter: float
    slot_length: float | None = Field(default=None, description="Second dimension for oval drills")
    offset: Point | None = None


class Pad(_Model):
    number: str
    type: PadType
    shape: str
    position: Point
    rotation: float = 0.0
    size: Point
    layers: list[str]
    net: str | None = None
    drill: Drill | None = None
    id: str | None = Field(default=None, description="Stable reference (schema 1.1+)")
    uuid: str | None = None
    roundrect_ratio: float | None = Field(default=None, description="Corner radius / smaller side (roundrect pads)")
    clearance: float | None = Field(default=None, description="Pad-local copper clearance override")
    solder_mask_margin: float | None = None
    solder_paste_margin: float | None = None
    solder_paste_ratio: float | None = None
    zone_connection: str | None = Field(default=None, description="inherited | none | thermal | solid | thru_hole_only")


class Graphic(_Model):
    """A non-electrical drawing primitive (outline, silkscreen, courtyard...)."""

    kind: str = Field(description="line | arc | circle | rect | polygon")
    layer: str
    width: float = 0.0
    points: list[Point] = Field(
        description=(
            "line: [start, end]; arc: [start, mid, end]; circle: [center, point_on_circle]; "
            "rect: [corner, opposite_corner]; polygon: vertices"
        )
    )
    filled: bool = False


class Component(_Model):
    reference: str
    value: str | None = None
    footprint: str
    layer: str
    side: Side
    position: Point
    rotation: float = 0.0
    attributes: list[str] = Field(default_factory=list, description="e.g. smd, through_hole, dnp")
    properties: dict[str, str] = Field(default_factory=dict)
    pads: list[Pad] = Field(default_factory=list)
    graphics: list[Graphic] = Field(default_factory=list)
    uuid: str | None = None
    id: str | None = Field(default=None, description="Stable reference (schema 1.1+)")
    locked: bool = Field(default=False, description="Locked in the source tool (schema 1.1+)")


class Track(_Model):
    kind: str = Field(description="segment | arc")
    start: Point
    end: Point
    mid: Point | None = None
    width: float
    layer: str
    net: str | None = None
    length: float
    id: str | None = Field(default=None, description="Stable reference (schema 1.1+)")
    uuid: str | None = None
    locked: bool = False


class Via(_Model):
    position: Point
    diameter: float
    drill: float
    layers: list[str]
    net: str | None = None
    via_type: str = Field(default="through", description="through | blind | micro")
    id: str | None = Field(default=None, description="Stable reference (schema 1.1+)")
    uuid: str | None = None
    locked: bool = False


class KeepoutRules(_Model):
    """What a keep-out zone forbids. ``True`` = allowed, ``False`` = not allowed, ``None`` = not stated."""

    tracks: bool | None = None
    vias: bool | None = None
    pads: bool | None = None
    copper_pour: bool | None = None
    footprints: bool | None = None


class Zone(_Model):
    net: str | None = None
    layers: list[str]
    outline: list[Point]
    area: float = Field(description="Area of the outline polygon in mm²")
    filled: bool = False
    keepout: bool = False
    name: str | None = None
    id: str | None = Field(default=None, description="Stable reference (schema 1.1+)")
    uuid: str | None = None
    keepout_rules: KeepoutRules | None = None
    priority: int | None = None
    clearance: float | None = Field(default=None, description="Zone-to-other-copper clearance")
    min_thickness: float | None = None


class BoardOutline(_Model):
    graphics: list[Graphic] = Field(default_factory=list)
    closed: bool = False
    bbox: BoundingBox | None = None
    area: float | None = Field(default=None, description="Enclosed area (mm²) when the outline is closed")


class SourceInfo(_Model):
    format: str = Field(description="Adapter id, e.g. 'kicad'")
    format_version: str | None = None
    generator: str | None = None
    generator_version: str | None = None
    filename: str | None = None
    sha256: str = Field(description="SHA-256 of the exact source bytes")
    size_bytes: int
    y_axis: str = "down"


class StackupLayer(_Model):
    name: str
    type: str = Field(description="As in the source, e.g. 'copper', 'core', 'prepreg', 'Top Solder Mask'")
    thickness: float | None = None
    material: str | None = None
    epsilon_r: float | None = None
    loss_tangent: float | None = None


class Stackup(_Model):
    """The board's physical layer stack, top to bottom, exactly as declared in the source.

    Absent (``None`` on the design) when the source doesn't declare one; VIA never assumes one.
    """

    layers: list[StackupLayer]
    copper_finish: str | None = None
    dielectric_constraints: bool | None = None


class NetClass(_Model):
    """A net class as stored in the board file (legacy KiCad stores them there)."""

    name: str
    clearance: float | None = None
    track_width: float | None = None
    via_diameter: float | None = None
    via_drill: float | None = None
    nets: list[str] = Field(default_factory=list)


class DesignConstraints(_Model):
    """Design rules present *in the board file itself*.

    Only fields the adapter actually found are set; ``None`` means "not present
    in this source", never "zero". KiCad 6+ keeps most rules in the separate
    ``.kicad_pro`` project file, which Stage 1 does not ingest.
    """

    board_thickness: float | None = None
    pad_to_mask_clearance: float | None = None
    solder_mask_min_width: float | None = None
    pad_to_paste_clearance: float | None = None
    net_classes: list[NetClass] = Field(default_factory=list)


class NetStat(_Model):
    name: str
    pad_count: int = 0
    track_count: int = 0
    via_count: int = 0
    track_length: float = 0.0


class DesignStats(_Model):
    layer_count: int
    copper_layer_count: int
    net_count: int
    component_count: int
    pad_count: int
    smd_pad_count: int
    through_hole_pad_count: int
    track_count: int
    via_count: int
    zone_count: int
    total_track_length: float
    board_width: float | None = None
    board_height: float | None = None
    board_area: float | None = None
    board_thickness: float | None = None
    min_track_width: float | None = None
    min_via_drill: float | None = None
    min_via_diameter: float | None = None
    components_top: int = 0
    components_bottom: int = 0
    unconnected_pad_count: int = Field(0, description="Copper pads not assigned to any net")


class ParseWarning(_Model):
    code: str
    message: str


class PCBDesign(_Model):
    schema_version: str = SCHEMA_VERSION
    engine_version: str = ENGINE_VERSION
    source: SourceInfo
    title: str | None = None
    layers: list[Layer]
    nets: list[Net]
    components: list[Component]
    tracks: list[Track]
    vias: list[Via]
    zones: list[Zone]
    graphics: list[Graphic] = Field(description="Board-level drawings, excluding the outline")
    outline: BoardOutline
    constraints: DesignConstraints = Field(default_factory=DesignConstraints)
    stackup: Stackup | None = None
    bbox: BoundingBox | None = None
    stats: DesignStats
    net_stats: list[NetStat] = Field(default_factory=list)
    warnings: list[ParseWarning] = Field(default_factory=list)


__all__ = [
    "ENGINE_VERSION",
    "SCHEMA_VERSION",
    "BoardOutline",
    "BoundingBox",
    "Component",
    "DesignConstraints",
    "DesignStats",
    "Drill",
    "Graphic",
    "KeepoutRules",
    "Layer",
    "LayerKind",
    "Net",
    "NetClass",
    "NetStat",
    "PCBDesign",
    "Pad",
    "PadType",
    "ParseWarning",
    "Point",
    "Side",
    "SourceInfo",
    "Stackup",
    "StackupLayer",
    "Track",
    "Via",
    "Zone",
]
