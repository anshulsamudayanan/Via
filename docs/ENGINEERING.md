# VIA PCB Engine

Package: `services/pcb-engine` (`via_pcb`). Pure Python, depends only on Pydantic.

```python
from via_pcb import parse_pcb

design = parse_pcb("board.kicad_pcb")  # or parse_pcb(raw_bytes, filename="board.kicad_pcb")
design.stats.component_count
design.model_dump_json()  # persisted form
```

## Layers of the engine

| Module | Responsibility |
|---|---|
| `parser.sexpr` | Tokenise + build an S-expression tree. Iterative (no recursion limit), never evaluates input, reports line/column on errors. Knows nothing about PCBs. |
| `adapters.base` | `PCBAdapter` contract (`sniff`, `parse`) and `AdapterRegistry` (detect by extension + header). |
| `adapters.kicad` | KiCad semantics → normalized model. |
| `models` | The normalized `PCBDesign` model: the only thing the rest of VIA consumes. |
| `geometry` | Pure functions: rotation (Y-down convention), arcs through 3 points, legacy arc conversion, shoelace area, bounding boxes, Edge.Cuts outline assembly. |

## Normalized model conventions

- Millimetres, mm², degrees. Absolute board coordinates (footprint-local coordinates are resolved). KiCad's +Y-down axis is kept and recorded as `source.y_axis = "down"`.
- `schema_version` (semver) and `engine_version` are embedded in every design.
- `source.sha256` and `source.size_bytes` identify the exact input bytes.
- Fields that a source does not contain are `null`/empty, never zero-filled or guessed.
- `warnings[]` lists everything skipped or suspicious (codes below). Repeated warnings are capped at 5 per code plus a summary line.

## KiCad support matrix

Tested file versions: `20171130` (KiCad 5) … `20250324` (KiCad 9). Older files are attempted with an `old_version` warning; newer files with `new_version`.

| Data | Extracted | Notes |
|---|---|---|
| Board outline | ✅ | `Edge.Cuts` lines, arcs (modern and legacy centre/angle form), circles, rects, polygons, incl. footprint-level Edge.Cuts. Chained into loops; `closed` flag; area = largest loop − inner loops. Arcs are approximated at 10° steps for area (≈0.01% error). |
| Board dimensions | ✅ | From outline bounding box; falls back to content bounds if no outline (with `missing_outline` warning). |
| Thickness | ✅ | `(general (thickness))`. |
| Layers | ✅ | Index, name, kind (copper, silkscreen, mask, paste, adhesive, fab, courtyard, edge, margin, documentation, user), side, raw type, user name. Classification is by **name**, not index (KiCad 9 renumbered layers). |
| Nets | ✅ | Net table; when absent (expected in KiCad 10), net names are collected from pads. |
| Footprints | ✅ | `footprint` (6+) and `module` (5). Library id, reference, value, other non-empty properties, layer/side, position, rotation, attributes (`smd`, `through_hole`, `dnp`, `exclude_from_bom` …), uuid/tstamp. |
| Pads | ✅ | Number, type (smd, through_hole, npth, connect), shape, absolute position, rotation, size, layers (wildcards like `*.Cu` expanded), net, drill (round / oval slot, offset). |
| Footprint graphics | ✅ | `fp_line/arc/circle/rect/poly` transformed to board space; rotated rects become polygons. |
| Tracks | ✅ | Segments and arcs: start, end, mid, width, layer, net, length (true arc length). |
| Vias | ✅ | Position, diameter, drill, layers, net, type (through/blind/micro). |
| Zones | ✅ | Net, layers, outline polygon, outline area, filled flag, keep-out flag, name. Filled polygons are **not** stored (only the flag). |
| Board graphics | ✅ | `gr_line/arc/circle/rect/poly` on non-Edge layers. |
| Design constraints | ⚠️ partial | Only what the `.kicad_pcb` itself contains: thickness, `pad_to_mask_clearance`, `solder_mask_min_width`, `pad_to_paste_clearance`, legacy in-file net classes (KiCad 5). KiCad 6+ keeps rules in `.kicad_pro`, which Stage 1 does not ingest. |
| Text, dimensions, groups, images, 3D models | ❌ | Silently skipped (no electrical meaning for Stage 1). |
| Bezier curves (`gr_curve`, `fp_curve`) | ❌ | Skipped with `unsupported_curve` warning. |
| Unknown top-level objects | ❌ | Skipped with `unsupported_object` warning. |

### Assumptions to confirm against real exported boards (CP4)
- Pad `(at x y angle)`: the angle is absolute (includes footprint rotation) — KiCad 5–9 behaviour.
- Bottom-side footprint children are stored already mirrored, so only rotation + translation is applied.

## Warning codes

`missing_version`, `old_version`, `new_version`, `missing_layers`, `missing_outline`, `open_outline`, `unknown_net`, `unknown_pad_type`, `missing_reference`, `invalid_track`, `invalid_zone`, `unsupported_curve`, `unsupported_object`.

## Errors

- `AdapterNotFoundError` — no adapter recognises the file (wrong extension or header). Message lists supported extensions.
- `UnsupportedFormatError` — recognised but unusable: invalid UTF-8, malformed S-expression (with line/column), wrong root node.

## Adding a format

1. Implement `PCBAdapter` in `adapters/<format>.py` (`format_id`, `display_name`, `extensions`, `sniff`, `parse`).
2. Register it in `adapters/__init__.py:get_registry`.
3. Add fixtures + expected-value tests in `tests/engineering/`.

## Tests

- `tests/unit/pcb_engine/` — parser and geometry.
- `tests/engineering/` — fixtures parsed and checked against **hand-computed** expected values; failure modes.
- Fixture provenance and licences: `tests/engineering/fixtures/README.md`.
