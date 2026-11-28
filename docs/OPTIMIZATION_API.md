# VIA Optimize: API

Everything is under `/api/v1`. Errors use the standard envelope. Project-scoped data returns 404 without access.

| Method | Path | Role | Notes |
|---|---|---|---|
| POST | `/designs/{id}/optimization-runs` | editor, 60/h | `{objectives[], constraints?, options?, weights?, build_quantity?}` -> 202 (identical active run -> 200). `build_quantity` -> `403 consent_required` without owner consent, `503 supplier_unavailable` without a key |
| GET | `/designs/{id}/optimization-runs`, `/optimization-runs/{id}` | viewer | config, baseline, Pareto keys, `summary.phase`, `summary.analysis` |
| GET | `/optimization-runs/{id}/candidates`, `/optimization-candidates/{id}` | viewer | with changes, constraint results, score, lifecycle, `applied_revision` |
| GET | `/optimization-runs/{id}/compare?candidates=` | viewer | metrics, deltas, Pareto, dominance |
| GET | `/optimization-runs/{id}/report?format=json\|markdown` | viewer | calculated metrics, constraints, limitations, verification statement |
| POST | `/optimization-candidates/{id}/decision` | editor | `{status: accepted\|rejected, reason?}`; `409 not_validated`, `422 reason_required` |
| GET | `/optimization-modules` | signed-in | module declarations (implemented / partial / planned / unsupported) |
| GET | `/suppliers/status` | signed-in | `{provider, configured}` |
| GET / PUT / DELETE | `/projects/{id}/supplier-consent` | GET viewer; PUT, DELETE owner | `supplier_lookup` consent |

Stored statuses (unchanged): `proposed | awaiting_validation | validated | rejected | accepted`. The UI shows `validated` as "Passed VIA checks". Validation status: `passed | unverified | requires_rerouting | failed | manual`. Constraint results: `satisfied | violated | unverified | not_applicable`.

Migrations: `0009` (candidate record), `0010` (`supplier_lookup` consent scope). Both additive.
