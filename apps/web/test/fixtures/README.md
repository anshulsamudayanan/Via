`reference-board.json` is the engine's normalized output for
`tests/engineering/fixtures/via_reference_v8.kicad_pcb` (an original VIA fixture,
same licence as this repository). Regenerate with:

    .venv/bin/python -m via_pcb.cli --filename via_reference_v8.kicad_pcb < tests/engineering/fixtures/via_reference_v8.kicad_pcb

(take the `design` object from the output).
