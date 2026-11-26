# VIA PCB Analysis

Status: Stage 2, Milestone 2. The analysis framework is in place (docs/FINDINGS_SYSTEM.md) with
four starter checks. Milestone 3 adds KiCad's real DRC and VIA's deterministic geometry,
connectivity, placement and manufacturing checks; this document grows with them.

Code: `services/pcb-engine/src/via_pcb/analysis/` (engine, registry, context, findings, `checks/`).
Analyses read the stored normalized design (schema 1.1+) and never re-parse vendor files.

## Checks today

| Check (`id`, version) | What it checks | Source / verification | Severity |
|---|---|---|---|
| `board_outline` 1.0.0 | Edge.Cuts outline present and closed. For an open outline, marks every line/arc endpoint that no other outline piece shares (endpoints compared at 1 µm). Evidence: graphic count, unjoined endpoint count, the parser's own warning | VIA deterministic / verified (exact on the parsed outline) | high |
| `design_rules_source` 1.0.0 | KiCad 6+ boards analysed without their `.kicad_pro` (rules fall back to defaults). Not raised for KiCad 5 files, which keep rules in the board | VIA deterministic / verified | info |
| `pads_without_net` 1.0.0 | Copper pads (not NPTH) assigned to no net, one finding per component, with each pad as an object and a marker | VIA deterministic / verified as a fact. Whether it's a problem needs the schematic, and the explanation says so | low |
| `import_warnings` 1.0.0 | Parser warnings as findings: skipped data (invalid tracks or zones, curves, unknown objects) is `low`, other notes `info`. Outline and project-file warnings are left to the checks above | VIA deterministic / verified | low / info |

Clean real boards produce no false positives from these checks. The KiCad 9 `video` project
(imported as a `.zip`) yields only `pads_without_net` findings on unused IC pins (13 components),
which is a true observation of low severity.

## What is not analysed yet

- **Clearance, shorts, unconnected items, annular rings, zone fills:** these come from KiCad DRC in Milestone 3. VIA won't approximate them and call it DRC.
- **Placement, routing, manufacturing, thermal, power, signal integrity:** Milestone 3 (deterministic and labelled heuristics) and Milestone 4 (AI suggestions, labelled as unverified).
