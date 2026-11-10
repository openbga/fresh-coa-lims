# Architecture

Baseline: 2026-11-10. Product intent is in [product.md](product.md); source and tests define the implementation. Open Qual IQ adapts the conventional Django/PostgreSQL architecture and UI assets of Open Roots IQ without its environmental domain model. Versions live in `pyproject.toml`, `uv.lock` and vendored asset notices.

## Shape and boundaries

One Django monolith and PostgreSQL 17 serve one organization/site. Django sessions, forms, ORM, transactions and migrations provide the foundation. Server-rendered Bootstrap pages work without a separate frontend service; HTMX progressively enhances actions. Gunicorn and WhiteNoise serve the container. There is no workflow DSL, repository abstraction, tenant platform, queue or offline synchronization requirement.

| Boundary | Responsibility | Extension rule |
|---|---|---|
| `accounts` | Individual users and explicit role membership | Scientific authority remains separate from account administration |
| `core` | Rule revisions, PIN credentials, signatures, audit and common transition contracts | One integrator owns shared schema/services and migrations |
| `quality` | Minimal lot/sample/result journey | Preserve identity and revision references when richer domain modules arrive |
| `config`, shared templates/static | Routing, environment, application shell and design primitives | One integrator merges registered app routes/navigation |
| Future domain apps | Catalog/sampling, analytical/QC/OOS, stability/operations and reporting | Depend on shared contracts; do not duplicate signing or audit |

## Integrity contracts

Views and forms handle HTTP, CSRF and field errors. Explicit domain functions authorize transitions and enforce policy. Every mutation must have an actor and meaningful reason where required. Signed transitions lock/recheck the current record revision and relevant authority, then commit the state change, immutable signature and audit event in one database transaction. A stale request must fail rather than sign a different revision. Authorization is checked on the server; hidden buttons and `is_staff` are not release gates.

Rule revisions are separately approved and effective dated. Draft presets are editable seed data; approved historical content is preserved. This foundation requires finite approval intervals and rejects overlap; schedule a new non-overlapping revision before expiry. Automatic retirement and richer applicability resolution are pending. Decisions retain the exact revision/snapshot evaluated. Selection by product/material, activity, site and market and conflict resolution must remain explicit as applicability expands. Do not merge conflicting obligations by choosing whichever is least restrictive. Audit and independent review are universal invariants.

A signature stores the individual signer, meaning, server execution time and record revision/content binding. PIN credentials use Django password hashing, never reversible storage. PIN verification is rate limited through persistent failure/lock state; failure events must survive rejection of the scientific transition. Successful PIN entry is authorization for the immediate checked action, not a reusable approval token. Do not log submitted PINs. Revocation, account recovery, session controls and identity verification require deployment procedures and further validation for covered use.

No user reviews their own authored scientific work, even if they also hold reviewer or administrator roles. Account/privilege changes need attributed audit events. Audit review must identify the records/range reviewed, reviewer, time and outcome; opening the audit page is not itself evidence of review.

Append-only history is enforced with PostgreSQL triggers as well as service boundaries. Database owners can alter triggers: this is protection against ordinary application writes, not cryptographic proof against a database administrator. Use separate migration and runtime credentials in production, least privilege, restricted database access and tested backups. Additive corrections/amendments preserve originals. No deletion/retention-disposal path is enabled by this foundation.

Scientific values use Decimal/numeric with explicit units, limits and original provenance. Never turn missing or nondetect values into zero. Later modules must freeze method/specification revisions, calculation inputs and review evidence. Reports must store immutable snapshots and issued bytes/checksums; downloads must not regenerate from mutable current records. Instrument files and persistent attachments must not rely on Render's ephemeral filesystem.

## Operation and deployment

| Item | Contract |
|---|---|
| Local database | Compose PostgreSQL 17 on loopback port 55433, separate from Open Roots IQ's 55432 |
| Render web | `open-qual-iq`, Docker, 1c-2g, Virginia, automatic deployment off |
| Render database | `open-qual-iq-db`, PostgreSQL 17, 0.5c-1g, 5 GB, private access |
| Migration | Fresh project history; serialized pre-deploy `python manage.py migrate --noinput` |
| Health | `/health/` process health; `/ready/` checks database availability |
| Static | Vendored local assets; `collectstatic` during build and before template tests |
| Security | Production secret/hosts/origins from environment, HTTPS, secure cookies and CSRF |
| Time | UTC default; retain unambiguous timestamp/zone context; never reinterpret signed records |

Resource sizes above are user-authorized configuration, not a claim of deployment or current provider pricing. Secrets and operational evidence stay out of Git. Seeding is deliberate and never part of deploy. Use backward-compatible migrations when instances overlap; reverting code does not revert schema. Restore into an isolated database and verify audit/signature/record relationships before relying on recovery. Production requires an owner for backup retention, restore rehearsal, access reviews, identity proofing and intended-use validation.

## Integration gate

Run Ruff, PostgreSQL pytest, Django checks, migration drift checks and collectstatic. Contract tests prioritize denied/self-review actions, effective rules, stale revisions, PIN failure/lockout, atomic rollback, immutability and failed/incomplete disposition. Run a headless synthetic journey with distinct actors and inspect keyboard access and error behavior. The integrator owns shared files and runs the combined gate once after independent packages pass focused checks. Passing development tests is not regulated-system validation.
