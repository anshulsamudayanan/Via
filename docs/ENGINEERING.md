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
- `schema_version` (semver) and `engine_version` are embedded in every design. Current: schema **1.1.0**, engine 0.2.0. Designs stored with 1.0.0 still load (all 1.1 fields are optional).
- `source.sha256` and `source.size_bytes` identify the exact input bytes (for a project archive: the `.zip` as uploaded; `source.board_file` and `source.project_files` name the members used).
- **Object identity (1.1):** components, pads, tracks, vias and zones carry `uuid` (exactly as in the source, `null` when absent: KiCad 5 tracks and vias, pads before KiCad 8) and `id`, a stable reference within the design: the source UUID when present and unique, otherwise a content-derived id (`trk:…`, `via:…`, `fp:…`, `zone:…`; pads `<component id>/pad:<number>`), with `~n` for duplicates. Re-parsing the same file gives the same ids. KiCad's DRC reports objects by UUID, so its findings map onto these ids.
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
| Footprints | ✅ | `footprint` (6+) and `module` (5). Library id, reference, value, other non-empty properties, layer/side, position, rotation, attributes (`smd`, `through_hole`, `dnp`, `exclude_from_bom` …), uuid/tstamp, `locked` (bare token in KiCad ≤ 7, `(locked yes)` in 8+). |
| Pads | ✅ | Number, type (smd, through_hole, npth, connect), shape, absolute position, rotation, size, layers (wildcards like `*.Cu` expanded), net, drill (round / oval slot, offset), uuid, roundrect ratio, local clearance, solder mask/paste margins and paste ratio, zone connection. Custom pad primitives and chamfer settings are not modelled. |
| Footprint graphics | ✅ | `fp_line/arc/circle/rect/poly` transformed to board space; rotated rects become polygons. |
| Tracks | ✅ | Segments and arcs: start, end, mid, width, layer, net, length (true arc length), uuid, `locked` (KiCad 6+; KiCad 5's status-bit lock isn't read). |
| Vias | ✅ | Position, diameter, drill, layers, net, type (through/blind/micro), uuid, `locked`. KiCad 5 omits the drill when a via uses its net class default: VIA resolves it from the net's class `via_drill` (else `setup via_drill`) and notes `via_default_drill` (found in Stage 2: 750 of 815 vias in the KiCad 5.1 `video` demo had been recorded with drill 0). |
| Zones | ✅ | Net, layers, outline polygon, outline area, filled flag, keep-out flag and rules (tracks, vias, pads, copper pour, footprints: allowed / not allowed), name, uuid, priority, clearance, minimum thickness. Filled polygons are **not** stored (only the flag). KiCad's DRC (Stage 2) checks the fills as stored in the file; KiCad 9.0.6's CLI doesn't refill them. |
| Stackup | ✅ | `(setup (stackup ...))`: each layer's name, type, thickness, material, εr, loss tangent; copper finish; dielectric constraints. Only the first sub-layer of a multi-material dielectric is recorded (`stackup_sublayers` warning). No stackup in the file → `null`, never assumed. |
| Board graphics | ✅ | `gr_line/arc/circle/rect/poly` on non-Edge layers. |
| Design constraints | ✅ with a project archive; ⚠️ board file alone | From the board file: thickness, `pad_to_mask_clearance`, `solder_mask_min_width`, `pad_to_paste_clearance`, legacy in-file net classes (KiCad 5). From a project `.zip` (see below): board-wide minimums, net classes with resolved nets, custom rules. `constraints.rules_source` says which (`board_file` or `project_file`). |
| Text, dimensions, groups, images, 3D models | ❌ | Silently skipped (no electrical meaning for Stage 1). |
| Bezier curves (`gr_curve`, `fp_curve`) | ❌ | Skipped with `unsupported_curve` warning. |
| Unknown top-level objects | ❌ | Skipped with `unsupported_object` warning. |

## Board viewer (Checkpoint 5)

The web viewer renders `GET /api/v1/pcb/{design_id}/normalized` through its own render model
(`apps/web/lib/pcb/render-model.ts`); the normalized model never changes for rendering.

| Drawn | How |
|---|---|
| Board outline | `Edge.Cuts` graphics (lines, arcs, circles, rects, polygons) |
| Tracks | Segments and arcs (arcs sampled at 8° chords; < 0.003 mm error on the test arc), true widths |
| Pads | Rotated outlines on every copper layer they're on: `circle` as a circle, `oval` as a stadium, everything else (`rect`, `roundrect`, `trapezoid`, `chamfered_rect`, `custom`) as its rotated bounding rectangle. Corner radii and custom pad primitives aren't in the normalized model, so they aren't drawn |
| Drills | Round and slotted (oval) holes, punched out in the background colour |
| Vias | Annular ring + drill |
| Zones | Outline polygon at low opacity. Filled copper isn't stored, so pours are not shown as filled areas (stated in the viewer) |
| Silkscreen, fab, courtyard, mask, paste, user layers | Their graphics; text is not parsed, so it isn't drawn |
| Components | Selection box from the courtyard (falls back to fab/silk graphics, then pads) |

Performance (Chromium, 1440×900): the 8k-track `video` board renders at about 32 ms per
zoom step. Boards with more than 40,000 tracks + pads switch to a snapshot preview while you
zoom or pan and redraw in full detail when you stop (351k tracks: about 31 ms per
interactive frame instead of about 536 ms).

### Loading off the main thread and overlays (Stage 2, Milestone 7)

- **Web Worker.** `lib/pcb/board-loader.ts` loads the board in a Web Worker
  (`lib/pcb/board.worker.ts`). The worker fetches the normalized design (same origin, session cookie),
  parses the JSON and builds the render model there. Only the render model and stats come back, so a
  large board no longer freezes the page while it loads. The parsed design stays in the worker, which
  computes net highlights on request. Without `Worker` (tests, or a worker that fails to start), the
  same code runs on the main thread.
- **Overlays.** `lib/pcb/overlay.ts` and `drawOverlay` in the renderer draw, on top of everything else:
  - a finding's region (its bounding box, dashed, in the severity colour, plus its points);
  - the components it names (outlined);
  - the copper of the nets it names: tracks, vias and pads. Arcs are drawn as two chords through
    their midpoint.

  Selecting a finding zooms to all of this. Geometry comes only from the parsed design and the
  finding's stored region.

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

## KiCad project archives (Stage 2, Milestone 1)

KiCad 6+ stores design rules and net classes in `<name>.kicad_pro` and custom rules in
`<name>.kicad_dru`. Without them, rule checks use KiCad's defaults: on the KiCad 9 `video` demo,
KiCad's own DRC reported 54 false violations without the project file and none with it
(docs/STAGE_2_AUDIT.md §5). So VIA accepts a `.zip` of the project (`via_pcb/project.py`):

- **Board selection:** the only `.kicad_pcb`; with several, the one with a matching `.kicad_pro`; otherwise refused (ambiguous). KiCad's `*-backups/` folders, hidden files and `__MACOSX` are ignored.
- **`.kicad_pro`:** `board.design_settings.rules` → `constraints.rules` (only known keys with the right JSON type; nothing is coerced). `net_settings.classes` → net classes (clearance, track width, via size/drill, microvia size/drill, diff-pair width/gap). Nets are resolved per class from KiCad 6's per-class `nets` lists, KiCad 8's `netclass_assignments`, or KiCad 7+'s `netclass_patterns` (wildcards `*` and `?`, case-sensitive). Unmatched nets go to `Default`.
- **`.kicad_dru`:** each rule's name, condition, layer, severity and constraints. Values are converted to mm only when a unit is written (`mm`, `mil`, `in`, `um`). The raw text is always kept. VIA records custom rules and doesn't evaluate them; KiCad's DRC does (Milestone 3).
- **KiCad 5 `.pro`** (INI) isn't read (`legacy_project_file` warning); a board with no project file gets `missing_project_file`.
- **Safety:** never extracted to disk; at most 5,000 entries; members over 1 MiB with a compression ratio above 200 are refused (zip bombs); encrypted entries, absolute paths, drive letters and `..` are refused; the board may be at most `VIA_MAX_UPLOAD_BYTES` uncompressed (checked from the central directory at upload and again while reading in the sandbox, in case the declared size lies); project/rule files at most 16 MiB.
- **Validation:** real KiCad 6.0–9.0 projects for both demos. KiCad 6 (explicit lists) and 7+ (patterns) resolve to the same classes on each board. (The 8.0 demo re-imported BUS1, after which `+12V` became `unconnected-(BUS1-+12V-PadA2)`, so the boards really differ: `tests/engineering/test_kicad_project.py`.)

## Warning codes

`via_default_drill`, `via_drill_unknown`, `missing_version`, `old_version`, `new_version`, `missing_layers`, `missing_outline`, `open_outline`, `unknown_net`, `unknown_pad_type`, `missing_reference`, `invalid_track`, `invalid_zone`, `unsupported_curve`, `unsupported_object`, `footprint_side`, `stackup_sublayers`; for project archives `missing_project_file`, `legacy_project_file`, `invalid_project_file`, `invalid_rules_file`.

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
