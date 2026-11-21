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
- Rotations (components, pads) are normalized to `[0, 360)`; positive is counter-clockwise on screen.
- `schema_version` (semver) and `engine_version` are embedded in every design.
- `source.sha256` and `source.size_bytes` identify the exact input bytes.
- Fields that a source does not contain are `null`/empty, never zero-filled or guessed.
- `warnings[]` lists everything skipped or suspicious (codes below). Repeated warnings are capped at 5 per code plus a summary line.

## KiCad support matrix

**Validation status.** The adapter has been validated against real KiCad-generated boards
from KiCad **5.1.12, 6.0.11, 7.0.11, 8.0.8 and 9.0.0** (two official demo projects per
release: `pic_programmer`, 2 copper layers, 63 footprints; `video`, 4 copper layers,
189 footprints, ~8k tracks). That is evidence for those releases and board styles, **not a
claim of full KiCad 5–9 compatibility**. Features those boards don't use (blind/micro vias,
keep-out zones, KiCad 9 layer numbering with more than 2 copper layers, custom pad shapes) are
covered only by hand-authored fixtures or not at all.

Accepted file versions: anything that parses. Outside `20171130`…`20250324` a
`old_version`/`new_version` warning is added.

| Data | Extracted | Notes |
|---|---|---|
| Board outline | ✅ | `Edge.Cuts` lines, arcs (modern and legacy centre/angle form), circles, rects, polygons, incl. footprint-level Edge.Cuts. Chained into loops; `closed` flag; area = largest loop − inner loops. Arcs are approximated at 10° steps for area (≈0.01% error). |
| Board dimensions | ✅ | From outline bounding box; falls back to content bounds if no outline (with `missing_outline` warning). |
| Thickness | ✅ | `(general (thickness))`. |
| Layers | ✅ | Index, name, kind (copper, silkscreen, mask, paste, adhesive, fab, courtyard, edge, margin, documentation, user), side, raw type, user name. Classification is by **name** (KiCad 9 renumbered layers), plus the layer **type**: KiCad 5 allowed renaming copper layers (e.g. `top_layer`), so any `signal`/`power`/`mixed`/`jumper` layer is copper; renamed legacy copper layers get their side from the fixed KiCad 5 ordinals (0 front, 31 back). |
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

## Running inside VIA (Checkpoint 4)

The API never parses in-process. The worker runs `python -I -B -m via_pcb.cli --filename <name>`
in a sandbox (`apps/api/src/via_api/parsing/sandbox.py`): file bytes on stdin, one JSON object
on stdout (`{"ok": true, "design": ...}` or `{"ok": false, "error": {code, message}}`), validated
against `PCBDesign` before anything is stored. See docs/SECURITY.md for the sandbox limits.

### Performance and memory (measured)

| Input | Content | Peak RSS | Time (parse + JSON) |
|---|---|---|---|
| 6.2 MB | KiCad 8 `video` demo: 189 footprints, 7,932 tracks, 808 vias | 160 MB | 1.5 s |
| 45 MB | synthetic: reference board + 351,408 segments | 1.65 GB | 15 s |

Peak memory is roughly **35× the file size** (S-expression tree + Pydantic models + JSON
output). The worker's default limit is therefore 3 GiB (`VIA_PARSER_MEMORY_LIMIT_MB`), which
covers the 50 MB upload limit; larger limits need more memory per worker. Reducing the engine's
memory footprint (streaming tokenizer, slots-based nodes) is future work.

## Real-board validation (Checkpoint 2)

Run `python scripts/fetch_real_fixtures.py` to download the boards (pinned by tag and SHA-256,
listed in `tests/engineering/real_fixtures.json`). They are CC BY-SA 4.0, so they live in the
git-ignored `tests/engineering/real/` folder and are never committed; see
`tests/engineering/fixtures/README.md`. `tests/engineering/test_real_kicad_boards.py` checks:

1. **Counts vs an independent text scan:** footprints, segments, arc tracks, vias, zones and nets counted by regex on the raw file must equal the parser's counts. No warnings, closed outline.
2. **Cross-version stability:** reference designators, copper layer count and bottom-side component count are identical across all five releases. Placement is identical for 7.0 → 8.0 → 9.0. The demos were edited between 5.1 and 7.0, and three footprints (P3, BUS1, POT1) were re-imported from updated libraries in 8.0, with different raw local pad coordinates. These were traced by hand in the raw files.
3. **Electrical consistency:** for every routed pad on a net without a copper zone, a track of the same net must end inside the pad (≥ 99% required; observed 100%). A wrong rotation or pad transform would break this immediately.

### Pad angle investigation

*Question:* is a pad's stored `(at x y angle)` angle absolute (footprint rotation included) or relative?

*Method:* for every pad in a rotated footprint in the ten real boards, compare the stored pad angle with the footprint angle.

*Findings:*
- 100% of pads either equal the footprint angle, or differ by their own intrinsic rotation (e.g. +90° for QFP side pads). The angle is **absolute**.
- In KiCad 5/6 files, a TQFP-100 rotated −90° has 50 pads with **no angle at all**. Those are pads with local +90°, so absolute −90 + 90 = 0, and KiCad omits a zero angle. **A missing angle therefore means 0°, not the footprint angle.** The Checkpoint 1 code fell back to the footprint angle, which was wrong for these pads; fixed and covered by `test_kicad_edge_cases.py` and `test_pad_angles_are_absolute_and_missing_means_zero`.
- Pad *positions* (local coordinates rotated by the footprint angle and translated) are confirmed by the track-endpoint check above, for both top and bottom footprints.
- Bottom-side footprint children are stored pre-mirrored: confirmed indirectly, since bottom-side pads in `video` (103 bottom components) pass the track-endpoint check with rotation + translation only.

### Bugs found by real boards
| Bug | Effect | Fix |
|---|---|---|
| Renamed KiCad 5 copper layers (`top_layer`, `bottom_layer`) classified as `user` | `copper_layer_count = 0`; bottom components reported as top; `*.Cu` expanded to nothing | Copper by layer type; side via the layer table |
| Missing pad angle fell back to footprint angle | Wrong pad orientation for pads whose absolute angle is 0 | Missing angle = 0° |

## Warning codes

`missing_version`, `old_version`, `new_version`, `missing_layers`, `missing_outline`, `open_outline`, `unknown_net`, `unknown_pad_type`, `missing_reference`, `invalid_track`, `invalid_zone`, `unsupported_curve`, `unsupported_object`, `footprint_side`.

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
