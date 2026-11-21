# VIA Security & Privacy

Status: design agreed at Checkpoint 1. Items are marked ✅ (implemented and tested)
or *(planned, CPn)*.

## Threat model (Stage 1)
| Asset | Threats | Controls |
|---|---|---|
| User accounts | Credential stuffing, brute force, session theft | Argon2id hashing; rate limiting on auth endpoints; httpOnly + Secure + SameSite=Lax session cookies; server-side revocable sessions storing only token hashes *(CP3)* |
| Private designs | IDOR / cross-user access, enumeration | Authorization checked in the service layer for every project-scoped request; unauthorized resources return `404` (not `403`) to avoid leaking existence; UUIDs; isolation regression tests *(CP3/CP4)* |
| Upload pipeline | Malicious files, resource exhaustion, path traversal | Size limit enforced while streaming; extension + header sniff; server-generated storage keys; parser never executes input (pure-Python tokenizer, non-recursive, warning caps ✅); parsing in a subprocess with CPU/memory/time limits and an empty environment, outside the API process *(CP4)* |
| Object storage | Public exposure | Private bucket; access only through the API (or short-lived presigned URLs after authorization); credentials from the environment *(CP2/CP4)* |
| Database | SQL injection | SQLAlchemy parameterized queries only; no raw string SQL *(CP2)* |
| Browser | CSRF, XSS | Same-origin API via rewrite; SameSite=Lax; required custom header on unsafe methods; React escaping; no `dangerouslySetInnerHTML` for user data; strict CORS allowlist *(CP2/CP3)* |
| Secrets | Leakage | Only environment variables; `.env` git-ignored; `.env.example` contains placeholders only ✅ |
| Errors | Information disclosure | Consistent error envelope; internal errors logged with a request id, never returned to clients *(CP2)* |

## Audit logging *(CP3)*
`activity_logs` records sensitive operations: register, login success and failure, logout,
session revocation, password reset request and completion, project create, rename,
archive and delete, membership changes, uploads (accepted and rejected), and parse results.

## Privacy & consent
- Uploaded files are **never** automatically contributed to VIA Learn or used for model training.
- `data_consents` records explicit, scoped, revocable consent. No consent is granted by default and Stage 1 has no flow that uses it *(CP2 schema)*.
- AI providers are disabled unless configured. Any future operation that sends project data to an external model must be user-initiated and authorized per project *(CP5 interfaces)*.

## Future hardening (post Stage 1)
Parser in a separate no-network container (gVisor/Firecracker), Postgres row-level security, 2FA/WebAuthn, malware scanning of uploads, signed and expiring download URLs everywhere.
