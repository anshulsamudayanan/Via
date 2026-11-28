# VIA Intelligence (AI)

Status: Stage 2, Milestone 4. Code: `services/ai-engine/src/via_ai/` (providers, routing, context,
`schemas.py`, `prompts.py`, `orchestration.py`, `verification.py`, `evaluation.py`) and
`apps/api/src/via_api/{ai,services/intelligence.py,routes/intelligence.py}`.

**AI is off by default** (`VIA_AI_PROVIDER=none`): AI endpoints answer `503 ai_disabled`, and
nothing fabricates an answer in its place. Automated tests use a scripted provider.

## Provider: Groq
VIA's AI runs on **Groq** (`services/ai-engine/src/via_ai/providers/groq.py`): set
`VIA_AI_PROVIDER=groq` and `GROQ_API_KEY` in `.env` (Compose passes both to the API and worker).
- **Transport:** Groq's OpenAI-compatible Chat Completions API (`https://api.groq.com/openai/v1`), called with the standard library; no SDK or extra dependency. The API and worker need outbound HTTPS to `api.groq.com`.
- **Model:** `VIA_AI_MODEL` (default `openai/gpt-oss-120b`), with per-task overrides `VIA_AI_MODEL_<TASK>`. `VIA_AI_EFFORT` maps to Groq's `reasoning_effort` for the `openai/gpt-oss-*` models (low, medium, high; `xhigh` and `max` become high); other models get no effort parameter.
- **Structured output:** `response_format: json_schema` from the Pydantic schema, then validated by that schema; a reply that doesn't validate is rejected, never repaired.
- **Refusals** (`message.refusal`, or `finish_reason: content_filter`) become `422 ai_refused`. Groq has **no embeddings**, so features that need vectors report that the provider can't do it.
- **Key handling:** read from the environment at startup, sent only in the `Authorization` header, never logged or shown in reprs. The parser sandbox runs with an empty environment, so uploaded files are never processed next to the key. Selecting Groq without a key leaves AI off, with a warning in the log.
- **Data:** Groq is an external provider, so the project owner's `external_ai_processing` consent is required before any project context is sent (see Consent below).

The Anthropic provider is still available (`VIA_AI_PROVIDER=anthropic`, optional SDK, `ANTHROPIC_API_KEY`) but is not the default.

## What it does
| Feature | Endpoint | Output |
|---|---|---|
| Explain the design, optionally focused on a finding, component, net or region (`x1,y1,x2,y2` mm) | `POST /designs/{id}/ai/explain`, `POST /findings/{id}/explain` | `Explanation`: answer, key points, references, numbers used (with their source), uncertainties, suggested validation |
| Design review | `POST /designs/{id}/ai/review` (editor) | `DesignReview`: summary; sections (layout, routing, placement, manufacturability, electrical, design rules), each listing the analysis findings that belong there *separately* from the model's hypotheses (each with confidence and how to validate it); up to 20 recommendations |
| Recommendations | `GET /designs/{id}/recommendations`, `PATCH /recommendations/{id}` | Problem, proposed change, rationale, expected benefits, trade-offs, required validation, evidence finding ids, references, numbers, confidence and uncertainty. A person can mark one accepted or rejected; that records a decision and never changes the design |

Every AI result is labelled `source: ai_suggestion` and `verification: unverified`. It is never presented as a verified result.

## What the model sees
Built by `DatabaseContextProvider` from database rows only. It never includes source files, normalized geometry, storage keys or user emails:
- **Board summary:** stats, layers, net names (≤ 1,000) and components (≤ 500).
- **Analysis findings** from the latest successful run of the current revision (or a chosen run): ≤ 200 findings, each with its evidence lines, source and verification level.
- **Design rules** from the project file, with `rules_source`.
- **The focused object's details:**
  - a finding's explanation;
  - a component's footprint, position and properties;
  - a net's counts and length;
  - the components inside a region.
- **Component records** matching the design's parts, each spec with its source and verified/unverified flag.

Truncation is reported in `truncated`.

**Consent:** for providers that send data off VIA's infrastructure (`external`), the project owner must grant `external_ai_processing` consent (`403 consent_required` otherwise). Revoking it takes effect immediately.

## Grounding verification (`verification.py`)
Before anyone sees an output, VIA checks it against the exact context sent. The output is **rejected** if it:
- cites a component, net, layer or finding id that isn't in the context;
- mentions a reference designator in its text that isn't in the design;
- reports a number (`numbers_used`) that appears nowhere in the context (relative tolerance 0.1 %).

Rejected outputs return `502 ai_output_rejected` with the problems listed, and are stored for audit.

What this proves and doesn't:
- It catches invented parts, nets, findings and measurements.
- It does **not** prove the reasoning is right, which is why outputs stay unverified suggestions with "required validation".

## Audit (`ai_outputs`)
Each request, accepted or rejected, records:
- the question, focus and analysis run;
- the provider, model and prompt version (`PROMPT_VERSION`);
- the SHA-256 of the canonical context JSON;
- the full structured output, the verification report and token counts.

## Prompts and models
- **Prompts:** in `prompts.py`. Changing any text bumps `PROMPT_VERSION`. The system prompt requires context-only answers, cited references and numbers, verified findings treated as facts and heuristic ones as indications, the model's own ideas labelled as hypotheses, and gaps stated as uncertainties.
- **Models:** routing picks a model per task (`explain`, `design_review`); a task can be overridden with `VIA_AI_MODEL_<TASK>`.
- **Output:** structured, via the provider's schema-validated output; a refusal is `422 ai_refused`.

## Component information (`component_records`)
- **Stored per project:** manufacturer, part number, description, package, specs, datasheet references, source and verification status. Each spec is `{name, value, unit, source, verified}`.
- **VIA never fills in specifications itself.**
- **Matching to the design:** components are matched by the part number in their footprint properties (`MPN`, `Manufacturer_Part_Number`, `Part Number`, …), optionally with a manufacturer (`GET /designs/{id}/component-matches`).
- **Datasheets:** stored as references with a URL and source. Automated retrieval from datasheets isn't implemented; any future importer must cite its sources.

## Evaluation (`evaluation.py`)
`evaluate(provider, cases)` reports the acceptance rate and the reasons for rejection.
- In tests it runs deterministically with the scripted provider (`tests/unit/ai`).
- An operator with a configured provider and consent can run it on real projects. It measures grounding, not engineering quality, which needs human review.

## VIA Learn knowledge in the context
Prompt version `2026-11-28.1`. For a design review or explanation, `DatabaseContextProvider` retrieves up to
3 approved VIA Learn entries (keyword search, 600 characters each, only entries whose contributor allowed AI
use) and puts them in `ProjectContext.knowledge`. The prompt says unverified entries are unconfirmed
suggestions and that cited entries must be listed with kind `knowledge`. The grounding check accepts a
`knowledge` citation only for an id that was retrieved. `ai_output_knowledge` records each entry shown and
whether it was cited; only a citation counts as influence. When the context exceeds the provider's input
budget, `fit_context` trims nets and components first, then knowledge, and findings last. See
[VIA_LEARN.md](VIA_LEARN.md).

## Rate limits
30 AI requests per user per hour.
