# VIA PCB Analysis

Status: Stage 2, Milestone 3. Code: `services/pcb-engine/src/via_pcb/analysis/` (engine, registry,
context, findings, `shapes.py` geometry kernel, `profiles.py`, `checks/`). The finding contract is
in docs/FINDINGS_SYSTEM.md.

Analyses read the stored normalized design (schema 1.1+) and never re-parse vendor files. The one
exception is KiCad DRC, which KiCad runs on the uploaded file itself.

## Where findings come from

| Source | What | Trust |
|---|---|---|
| **KiCad DRC** (`kicad_drc`) | KiCad 9.0.6's own rule checker on the uploaded board plus its `.kicad_pro`/`.kicad_dru` | `verified` with project rules (or KiCad 5 boards, whose rules are in the board); `heuristic`, confidence 0.6, when run with KiCad's defaults because no project file was uploaded |
| **VIA deterministic** | VIA's checks below, on exact geometry | `verified` when exact on data the model represents exactly; `heuristic` for rules of thumb or approximated shapes |
| **Calculated estimates** | IPC-2221 current capacity, IPC-2141 microstrip impedance | `heuristic`; run only with user inputs; formula, inputs and their sources in the evidence |
| **AI** | Milestone 4 | Never `verified` by itself |

## KiCad DRC

- **Where it runs:** in the `eda` service (official `kicad/kicad:9.0.6` image, pinned by digest).
- **What it receives:** the worker re-packs the upload in the parser sandbox into a bundle with fixed names: `board.kicad_pcb`, plus `board.kicad_pro` and `board.kicad_dru` when present.
- **What it runs:** `kicad-cli pcb drc --format json --units mm --severity-error --severity-warning`. Violations the designer excluded in KiCad stay excluded.
- **Zones are checked as filled in the file.** KiCad 9.0.6's CLI has no zone-refill option. That's the right check for manufacturing (stale fills are what gets made, and show up as violations), but refill zones in KiCad before uploading if you want fresh fills checked.
- **Mapping to VIA objects:** each item is matched by UUID. When KiCad generated the UUID at load time (KiCad 5–7 pads, KiCad 5 tracks), VIA falls back to "Pad N … of REF" or "Footprint REF" in KiCad's description. Unmapped items keep their description and position as evidence.
- **Severity:** shorts and crossing tracks → critical; other KiCad errors → high; KiCad warnings → medium; silkscreen, text and courtyard housekeeping → low. KiCad's own severity is kept in the evidence.
- **Suppressed** (they describe the server, not the design): `lib_footprint_issues`, `lib_footprint_mismatch` and `footprint_filters_mismatch`. Footprint libraries aren't installed in the container. The count is recorded in the check's details.
- **Unavailable or failed:** if the service is unreachable or fails, the check is skipped with the reason and the other checks still run. Without `VIA_EDA_URL` it is "KiCad DRC isn't configured".
- **Measured:**
  - The KiCad 9 `video` demo project yields 0 KiCad findings with its project file, and 54 false ones without (docs/STAGE_2_AUDIT.md §5).
  - Our reference board yields KiCad's real 2 shorts, 6 clearance, 3 hole-clearance and 4 mask-bridge errors.

## Geometry kernel (`shapes.py`)

Copper is modelled as *core + radius* shapes, so distances are exact for:
- round pads and vias;
- oval pads (stadiums);
- rectangles;
- rounded rectangles (the core is the rectangle shrunk by the corner radius);
- tracks (segments; arcs are split into chords with ≤ 2 µm sagitta).

Trapezoid, chamfered and custom pads use their bounding rectangle, and findings involving them are `heuristic`.

Other modelling details:
- Through vias carry copper on every layer between their end layers.
- Holes are round or slotted.
- The board edge is the Edge.Cuts outline, with arcs sampled to the same tolerance.
- Comparisons allow 1 µm for measurement error.

**Validation:** on the KiCad 6–9 `video` and `pic_programmer` demos, KiCad DRC with the project rules reports no clearance or unconnected items. VIA's spacing check at the net classes' 0.2 mm and its connectivity check also report none (`test_no_false_positives_on_kicad_clean_real_boards`).

## Checks

### Connectivity and layers
| Check | What | Severity / trust |
|---|---|---|
| `copper_islands` | Pads of one net that copper doesn't join (union-find over touching same-net copper). Pads with the same number in one footprint count as connected. Zone fills aren't stored, so a zone's outline stands in for its fill. Markers show the nearest pad pairs. **Skipped when KiCad DRC ran** (its unconnected-items check is authoritative) | high, `verified`; medium, `heuristic` when a zone or approximated pad is involved |
| `single_pad_nets` | Nets reaching one pad. KiCad's names for pins connected to nothing (`unconnected-…`, and KiCad 5's `Net-(REF-PadN)` on that same pad) are excluded | low |
| `copper_layer_usage` | Copper layers with no tracks, zones or SMD pads. Per-layer statistics go in the details | info |
| `pads_without_net` | Copper pads with no net (from Milestone 2) | low |

### Manufacturing (against a profile)
Findings are grouped by net, via size or component, with up to 100 objects and 50 markers each.

| Check | Measures | Severity |
|---|---|---|
| `mfg_track_width` | Track width vs `min_track_width` | medium |
| `mfg_vias` | Via drill, diameter and annular ring `(diameter − drill)/2` | medium |
| `mfg_pad_holes` | Pad drill; through-hole annular ring `(min side − hole)/2 − drill offset` (slots, offsets and odd shapes: `heuristic`) | medium |
| `mfg_hole_spacing` | Hole edge to hole edge, pads and vias, plated or not | medium |
| `mfg_copper_to_edge` | Pads, tracks and vias to the board outline (zones excluded; edge connectors and castellations are intentional exceptions) | medium |
| `mfg_copper_spacing` | Copper of different nets (pads, tracks, vias; zones left to KiCad DRC) | high |
| `mfg_silkscreen` | Silkscreen line width, grouped by layer and width (text isn't parsed) | low |

**Profiles:** VIA conservative (the default) and VIA advanced. Their values are typical, documented as not any manufacturer's specification. Projects can also store their own profiles (`/projects/{id}/manufacturing-profiles`). Every run copies the exact profile values it used into its config, so later edits don't rewrite history.

| | conservative | advanced |
|---|---|---|
| Track / clearance | 0.15 / 0.15 | 0.10 / 0.10 |
| Drill / via diameter / annular ring | 0.30 / 0.60 / 0.15 | 0.20 / 0.45 / 0.10 |
| Hole to hole / copper to edge / silkscreen | 0.50 / 0.30 / 0.15 | 0.25 / 0.20 / 0.10 |

### Placement and board space (measured exactly; meaning heuristic)
| Check | What | Severity |
|---|---|---|
| `placement_orientation` | Components at angles that aren't multiples of 90° | info |
| `connector_edge_access` | Connectors (J/P/CN/X/USB, or connector footprints) whose footprint is more than max(5 mm, 10 % of the board's smaller side) from every edge | low, confidence 0.5 |
| `decoupling_proximity` | IC (U/IC) power pins, identified by net name, with no capacitor (C, 2 pads, power-to-ground) within 5 mm pad to pad (option `decoupling_max_distance_mm`) | low, confidence 0.6 |
| `board_space` | Margins between the component extent (courtyards, else pads) and the outline. Large margins are reported with the size a 2 mm margin would give | info |

### Routing and electrical
| Check | What | Severity |
|---|---|---|
| `routing_detour` | Routed length more than 2× the Euclidean minimum spanning tree of the net's pads (MST ≥ 5 mm; nets with zones excluded; 20 worst nets) | info, confidence 0.5 |
| `netclass_track_width` | Tracks narrower than their net class's width (needs the project file; KiCad treats it as a default, not a minimum) | low |
| `track_current_capacity` | **Inputs:** `options.power.nets` (amps per net), `temperature_rise_c` (default 10), copper thickness from the stackup or `copper_thickness_mm`. IPC-2221: I = k·ΔT^0.44·A^0.725 (A in mil², k 0.048 outer / 0.024 inner). Layers without a known copper thickness are listed, not guessed | medium |
| `impedance_estimate` | **Inputs:** `options.impedance.nets` (Ω per net), `tolerance_pct` (default 10). Outer-layer microstrip only, from the declared stackup (adjacent dielectric height and εr, copper thickness), using IPC-2141 Z0 = 87/√(εr+1.41)·ln(5.98h/(0.8w+t)). Not estimated outside 0.1 < w/h < 2 or on inner layers (listed in the details) | medium |

### From Milestone 2
`board_outline`, `design_rules_source`, `import_warnings` (see docs/FINDINGS_SYSTEM.md).

## Not analysed (yet)
- **Zone fills:** not stored. Zone clearance, fill islands and thermal reliefs come from KiCad DRC.
- **Stripline impedance, differential pairs, length matching:** not implemented.
- **Thermal simulation; current density in planes:** not implemented. IPC-2221 applies to tracks only.
- **Text and silkscreen-over-pad:** VIA doesn't parse text; KiCad DRC covers silkscreen over copper.
- **Functional grouping beyond decoupling:** not analysed; the optimizer's placement metrics (Milestone 5) are the next step.
