# Engineering test fixtures

Every fixture must have a clear licence that allows redistribution in this
repository. Record provenance here **before** adding a file.

| File | Source | Licence | What it exercises |
|---|---|---|---|
| `via_reference_v8.kicad_pcb` | Hand-authored for VIA (KiCad 8 syntax, file version 20240108) | Same as this repository | Rectangular outline, SMD + THT + NPTH pads, rotated bottom-side footprint, segment + arc tracks, via, filled zone, footprint graphics, setup rule |
| `via_legacy_v5.kicad_pcb` | Hand-authored for VIA (KiCad 5 syntax, file version 20171130) | Same as this repository | `module`/`fp_text`, unquoted tokens, legacy centre/angle arc in the outline, oval drill, in-file net class, unsupported bezier curve |
| `via_features_v9.kicad_pcb` | Hand-authored for VIA (KiCad 9 syntax, file version 20241229) | Same as this repository | Schema 1.1 fields: both `locked` syntaxes (footprints and tracks), `tstamp` vs `uuid`, duplicate UUID and identical uuid-less tracks (id derivation), pad margins/roundrect/zone connection, 4-layer stackup incl. a dielectric with sub-layers, keep-out rules, zone priority/clearance/min thickness. Not electrically meaningful. |
| `via_reference_v8.kicad_drc.json` | Output of `kicad-cli pcb drc --format json --severity-error --severity-warning --units mm` (KiCad 9.0.6, official image) on `via_reference_v8.kicad_pcb` (renamed `board.kicad_pcb`; `date` blanked) | Same as this repository (derived from our own board) | Real KiCad DRC report for testing the `kicad_drc` mapping: 2 shorts, 6 clearance, 3 hole clearance, 4 solder mask bridge errors, 4 footprint-library warnings (suppressed as environment checks) |

Expected values in `../test_kicad_fixtures.py` and `../test_model_v1_1.py` were derived by hand from these
files (see comments in the tests), not copied from parser output.

## Third-party real boards (not committed)

Licence policy (project owner decision, CP2): prefer CC0, CC-BY, MIT, CERN-OHL-P, which may be
committed here with provenance. Copyleft boards (GPL, CC BY-SA, CERN-OHL-S) may be used only
for isolated internal testing: fetched on demand, pinned by SHA-256, documented, never committed
or redistributed.

| Files | Source | Licence | Handling |
|---|---|---|---|
| `pic_programmer_<tag>.kicad_pcb`, `video_<tag>.kicad_pcb` for tags 5.1.12, 6.0.11, 7.0.11, 8.0.8, 9.0.0 | KiCad official demos, `gitlab.com/kicad/code/kicad`, `demos/<project>/<project>.kicad_pcb` at each tag | CC BY-SA 4.0 (per KiCad `LICENSE.README`) | Copyleft: internal testing only. `scripts/fetch_real_fixtures.py` → git-ignored `tests/engineering/real/`. Manifest with SHA-256: `../real_fixtures.json` |

Still wanted: permissively licensed (CC0/CC-BY/MIT/CERN-OHL-P) real boards that can be
committed, ideally with blind/micro vias, keep-outs and more than 2 copper layers on KiCad 9.
