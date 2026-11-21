# Engineering test fixtures

Every fixture must have a clear licence that allows redistribution in this
repository. Record provenance here **before** adding a file.

| File | Source | Licence | What it exercises |
|---|---|---|---|
| `via_reference_v8.kicad_pcb` | Hand-authored for VIA (KiCad 8 syntax, file version 20240108) | Same as this repository | Rectangular outline, SMD + THT + NPTH pads, rotated bottom-side footprint, segment + arc tracks, via, filled zone, footprint graphics, setup rule |
| `via_legacy_v5.kicad_pcb` | Hand-authored for VIA (KiCad 5 syntax, file version 20171130) | Same as this repository | `module`/`fp_text`, unquoted tokens, legacy centre/angle arc in the outline, oval drill, in-file net class, unsupported bezier curve |

Expected values in `../test_kicad_fixtures.py` were derived by hand from these
files (see comments in the tests), not copied from parser output.

## Pending: third-party real-world boards (CP4)

Acceptable licences: CC0, CC-BY, CERN-OHL-P, MIT, Apache-2.0. Copyleft
(GPL, CC-BY-SA, CERN-OHL-S) needs an explicit decision from the project owner
because the fixtures would be redistributed with the repository.
