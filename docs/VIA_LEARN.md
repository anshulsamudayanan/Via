# VIA Learn

Opt-in collective knowledge and a feedback loop for VIA's AI recommendations. Projects stay private by
default. Nothing is collected automatically: every shared item is something a person chose to write, or
reviewed and submitted themselves.

## What it does

| Area | Behaviour |
|---|---|
| Feedback | On any AI recommendation, editors can mark it helpful or not helpful, accept or reject it with a reason, and send a correction, an incorrect-assumption report or a comment. Each record stores recommendation, user, project, analysis run, category, type, time, explanation, and the model, prompt and engine versions. Acceptance is recorded but is not treated as proof of correctness. |
| Knowledge library | Nine categories (design pattern, component selection, routing, thermal, signal integrity, manufacturing, BOM and cost, optimization example, verified recommendation). Entries carry category, description, technical metadata, source, provenance, verification status, permissions, timestamps and a version. |
| Contributions | Any signed-in user can write an entry (rights confirmation required). The project owner can, with the separate Learn consent, draft an entry from a recommendation. Drafts are private until submitted. |
| Review | A `learn_reviewer` approves or rejects submissions and sets the verification level. Nobody reviews their own entry. |
| Withdrawal | The contributor can withdraw at any time. The entry leaves retrieval at once and its content is erased from the entry and every version row. The id, ownership and provenance rows stay. |
| Retrieval | Approved entries only, never project data. Verified entries rank above reviewed above unverified. Results carry attribution, and use in AI answers is logged. |
| Evaluation | Acceptance, rejection and helpful rates, grounding-rejection rate, a deterministic evidence-resolution check, grouped by category, model, prompt and engine version, and board-size bucket. |

## Stores and ownership

Private side (follows project access rules): `recommendation_feedback`, `ai_output_knowledge`.

Collective side: `learn_entries`, `learn_entry_versions`. These have foreign keys only to `users`,
`data_consents` and each other. They never reference projects, designs, revisions or files, so a
project's deletion or access change cannot reach them and they cannot be joined back to a project.
Alembic does not manage schemas, so the separation is a table prefix and a foreign-key rule.
**Not done:** a separate database role without access to the private tables (deferred infrastructure).

Migration: `20261128_0011_via_learn.py` (also `users.learn_reviewer`).

## Lifecycle

`draft → pending_review → approved | rejected`, and `withdrawn` from pending or approved.
Content is immutable after the draft. Approval is not verification. Verification is
`unverified`, `reviewed` or `verified`; `reviewed` and `verified` need a stated basis. Each verification
change bumps `version` and writes a version row.

- Free text from any signed-in user stays **unverified** until a reviewer says otherwise.
- Project-derived drafts need the owner's Learn consent **and** a per-item submit.

## Privacy: the deterministic scrub

Drafts made from a recommendation have reference designators, non-generic net names, project, design
and file names, UUIDs and file names removed (`services/learn_scrub.py`). Generic nets (GND, VCC, +5V…)
stay. A residual check returns `409 scrub_incomplete` if identifiers remain. Numbers are kept on
purpose, so the contributor must read the preview before submitting.

Known limits: a project name shorter than 3 characters is not scrubbed; a designator-shaped token such
as `R100K` is removed even though it is a value.

## Consent

Scope `via_learn_contribution` on `data_consents`, per project, granted by the owner, revocable.
It is independent of `external_ai_processing` and supplier pricing consent. Revoking can also withdraw
the project's existing contributions (`withdraw_existing`, default on). `POLICY_VERSION` is unchanged.

## Retrieval

PostgreSQL full-text search: a `tsvector` column with a GIN index and an OR-of-words query, ranked by
`ts_rank_cd` times a verification weight (verified 1.0, reviewed 0.7, unverified 0.4). It is **lexical,
not semantic**: the database has no pgvector and the Groq free tier has no embeddings. The API and UI
say so (`GET /learn/meta`).

In AI reviews, up to 3 entries (600 characters each, `ai_retrieval` permission on) are added to the
context. The prompt tells the model that unverified entries are only unconfirmed suggestions, and the
grounding check accepts only a retrieved entry id as a `knowledge` citation. `ai_output_knowledge`
records what was shown and whether it was cited. Only a citation counts as influence.

## Evaluation

`GET /learn/evaluation` (your projects, or one project) and `GET /learn/evaluation/global`
(reviewers; counts and rates only).

The evidence-resolution check asks whether the findings behind a recommendation (matched by fingerprint)
are absent from the latest analysed newer revision of the same design: `resolved`, `persisting` or
`not_checkable`. It shows a finding went away, not that the advice caused it.

**Not measurable, and labelled so in the API and UI:** false-positive and false-negative rates (no
ground truth) and accuracy by PCB type (no classification exists; a coarse layer-count and part-count
bucket is used instead).

## API (`/api/v1`)

| Method | Path | Who |
|---|---|---|
| POST | `/recommendations/{id}/feedback` | project editor+ |
| GET | `/learn/feedback` | signed in (own, or projects you can access) |
| GET | `/learn/meta`, `/learn/entries`, `/learn/entries/{id}`, `/learn/entries/{id}/versions` | signed in (approved entries, or your own) |
| POST | `/learn/contributions` | signed in, 60 writes/h |
| POST | `/recommendations/{id}/contribute` | project owner with Learn consent |
| GET | `/learn/contributions` | own |
| POST | `/learn/contributions/{id}/submit`, `/withdraw` | contributor |
| DELETE | `/learn/contributions/{id}` | contributor, drafts only |
| PUT | `/learn/contributions/{id}/permissions` | contributor |
| GET | `/learn/review` | reviewer |
| POST | `/learn/contributions/{id}/review` | reviewer, not own entry |
| PUT | `/learn/entries/{id}/verification` | reviewer, not own entry |
| GET/PUT/DELETE | `/projects/{id}/learn-consent` | member read, owner write |
| GET | `/learn/evaluation` | project member |
| GET | `/learn/evaluation/global` | reviewer |

Limits: feedback 120/h, library reads 600/h, writes 60/h per user. Writes are audited. Inaccessible
projects and other users' drafts return 404.

## Making a reviewer

Only the server CLI can: `via-api learn-reviewer <email>` (`--revoke` to remove). There is no API for it.

## Known limitations

- Keyword retrieval only; no semantic search.
- No separate database role for the collective store yet.
- Evaluation cannot measure false positives or negatives, or true per-PCB-type accuracy.
- Project-derived contributions keep numbers; the contributor's preview is the safeguard.
- The Groq free tier allows about one review a minute and a trimmed context. The UI does not yet show the trimming notice.
