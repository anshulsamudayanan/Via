# VIA Optimize: roadmap and capability status

| Capability | Status |
|---|---|
| Outline fit, via standardization, track minimum width | implemented |
| Area analysis, margin analysis | implemented |
| Power-track widening | partial (width for given currents only) |
| Placement (ratsnest), placement compaction | partial (no routability or congestion model; top-side parts; needs re-routing) |
| Layer reduction | partial (manual in KiCad) |
| BOM cost (Mouser) | partial (one supplier, exact MPN only, not live-verified at time of writing) |
| Component alternates | planned |
| Re-routing | unsupported (no autorouter) |
| Signal integrity, thermal simulation | unsupported |

Next: a second supplier behind the same `Offer` model, an alternates module with explicit user review, and routing-aware placement once a router exists.
Known limits: constraints VIA cannot evaluate are recorded as `unverified`, and a declared hard requirement of that kind blocks acceptance.
