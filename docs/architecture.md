# Architecture

Baseline: 2026-11-10. Product intent is in [product.md](product.md); source and tests define the implementation. OpenBGA Qualab uses a conventional Django/PostgreSQL architecture for manufacturing quality control. Versions live in `pyproject.toml`, `uv.lock` and vendored asset notices.

## Shape and boundaries

One Django monolith and PostgreSQL 17 serve one organization/site. Django sessions, forms, ORM, transactions and migrations provide the foundation. Server-rendered Bootstrap pages work without a separate frontend service; HTMX progressively enhances actions. Gunicorn and WhiteNoise serve the container. There is no workflow DSL, repository abstraction, tenant platform, queue or offline synchronization requirement.

| Boundary | Responsibility | Extension rule |
|---|---|---|
| `accounts` | Named users, signed account administration, explicit roles and session revocation | Scientific authority remains separate from account administration |
| `core` | Rule revisions, PIN credentials, signatures, audit and common transition contracts | One integrator owns shared schema/services and migrations |
| `quality` | Lot/sample identity and signed QC disposition; DEBUG-only legacy result journey | Native disposition locks the lot and consumes assignment, analytical and hold gates |
| `config`, shared templates/static | Routing, environment, application shell and design primitives | One integrator merges registered app routes/navigation |
| `catalog`, `sampling` | Approved method/specification/QC/sampling revisions and lot requirement snapshots | Publish bounded requirements; unsupported applicability must hold |
| `analytical` | Observations/corrections, replicates, batches/QC, OOS and controlled retests | Preserve original data and publish lot blockers/evidence under the lot lock |
| `laboratory`, `stability` | Resource eligibility/use, qualification, protocols/pulls, reserves, retention and holds | Publish explicit eligibility and hold/evidence contracts |
| `reporting` | Signed CoA issuance/amendments, immutable snapshots and stored PDF bytes | Consume native evidence and recheck hashes/gates under lock |

## Integrity contracts

Views and forms handle HTTP, CSRF and field errors. Explicit domain functions authorize transitions and enforce policy. Every mutation must have an actor and meaningful reason where required. Signed transitions lock/recheck the current record revision and relevant authority, then commit the state change, immutable signature and audit event in one database transaction. A stale request must fail rather than sign a different revision. Authorization is checked on the server; hidden buttons and `is_staff` are not release gates.

Rule revisions are separately approved and effective dated. Draft presets are editable seed data; approved historical content is preserved. This foundation requires finite approval intervals and rejects overlap; schedule a new non-overlapping revision before expiry. Automatic retirement and richer applicability resolution are pending. Decisions retain the exact revision/snapshot evaluated. Selection by product/material, activity, site and market and conflict resolution must remain explicit as applicability expands. Do not merge conflicting obligations by choosing whichever is least restrictive. Audit and independent review are universal invariants.

A signature stores the individual signer, meaning, server execution time and record revision/content binding. PIN credentials use Django password hashing, never reversible storage. PIN verification is rate limited through persistent failure/lock state; failure events must survive rejection of the scientific transition. Successful PIN entry is authorization for the immediate checked action, not a reusable approval token. Do not log submitted PINs. HTTP signing re-enters the username and PIN on each signing. Server-enforced idle and absolute lifetimes default to 900 and 28,800 seconds; old sessions lacking login timestamps are rejected. The immutable signature records the authentication channel/components and login time, never raw credentials/session cookies. Trusted in-process services are a separate PIN-only channel, not exposed as a web bypass. Revocation, recovery, identity verification and the deployment procedures still require validation for covered use.

| Authority | Read access | Mutation authority |
|---|---|---|
| Admin | All lab lists/details/history, rule sets, audit filter/export and CoA PDF | Account lifecycle only; scientific actions need the designated additional role |
| Analyst | Lab records through each module's shared READ roles | Receipt, sampling and analytical entry subject to eligibility and state checks |
| Reviewer | Lab records through shared READ roles | Independent review within the module's reviewer policy |
| Quality | Lab records, rules and audit | Configuration, disposition and other explicitly authorized quality actions |
| Auditor | Lab records and audit | Audit-review attestation only; no scientific record mutation |
| No recognized role, including a superuser alone | Account access guidance and own credential maintenance | No laboratory or in-app administrative authority |

Account web mutations use the explicit admin role and a fresh username/PIN signature with meaning `account_authorized`. An account revision, whitelisted non-secret before/after audit values and signature commit atomically. Passwords, PINs and their hashes are excluded from evidence. A transaction advisory lock serializes all account administration, including last-active-admin checks across different target rows; row locks and a revision check reject stale edits. Admins cannot grant themselves additional roles or deactivate/remove the last active admin. The sole self-assignment exception is trusted CLI bootstrap: an active roleless superuser can assign exactly admin when no active admin exists. Django staff/superuser flags cannot be changed through the web management pages.

Every administrative account change advances a session epoch. Middleware rejects older sessions; signing rechecks the locked actor's epoch and forced-password flag to close a mid-request revocation gap. An intentional self-change signs against the locked pre-change actor state and ends that session on success. New web accounts and password resets require password replacement before workspace access. A reset may retain the current password or install a privately shared temporary one; there is no email delivery. The owner's replacement uses current password plus reason, records an unsigned audit event, rotates the session, and preserves only that current session. Existing sessions without an epoch expire when this release is deployed. Trusted operator commands remain audited rather than PIN-signed; their execution environment is an operational privilege boundary.

No user reviews their own authored scientific work, even if they also hold reviewer or administrator roles. Account/privilege changes need attributed audit events. Audit review must identify the records/range reviewed, reviewer, time and outcome; opening the audit page is not itself evidence of review.

Append-only history is enforced with PostgreSQL triggers as well as service boundaries. Database owners can alter triggers: this is protection against ordinary application writes, not cryptographic proof against a database administrator. Use separate migration and runtime credentials in production, least privilege, restricted database access and tested backups. Additive corrections/amendments preserve originals. Retention obligations and disposal blockers are implemented, but no physical/electronic disposal action is enabled.

Scientific values use Decimal/numeric with explicit units, limits and original provenance. Never turn missing or nondetect values into zero. Catalog and sampling revisions are frozen into lot assignments and analytical requirement snapshots. The shared adapter delegates requirement translation to the catalog/sampling contract, then validates the analytical payload without supplying defaults. Native testing accepts numeric results with inclusive limits and declared replicate policy. A numeric reporting precision rounds the mean half-up; `reporting_decimals=null` preserves exact comparison. Submission rejects nonterminating or more-than-eight-decimal exact means. Individual replicate conformance is checked when configured. Qualitative values, exclusive limits and unsupported payloads remain holds, not guessed conversions.

Requirement reassignment is refused under the lot lock once any native test exists; there is no controlled supersession transition for that evidence yet. New batch creation resolves only currently effective approved method revisions, while assignment to a batch requires the test's exact frozen method revision. Older frozen tests therefore cannot acquire a newly created old-revision batch; this is an intentional hold, not automatic migration to the current method.

Every analytical evidence change locks and advances the quarantined lot revision. Disposition consumes current assignment requirements, analytical blockers and active stability/retention holds under that lock, then captures assignment and analytical evidence in the signed lot. Production cannot fall back to manually entered limits: that path is DEBUG-only without native assignments, and mixed native/foundation evidence is rejected. Independent review includes data authorship beyond the submitting user, including corrected originals and batch QC.

Observation creation and correction invoke the configured analyst eligibility hook inside their transaction. The adapter locks matching qualification rows, requires a current approved, non-revoked qualification for the test method code, and freezes user/activity/qualification evidence on the observation and audit event. No configured hook means observations are held. This is method-specific analyst authorization, not instrument/reagent selection: equipment/reagent use remains an explicit laboratory workflow, and the observation form does not enforce it. Batch QC recording/correction does not currently invoke this observation hook. Stability chamber use separately checks equipment eligibility. Preserve these boundaries when extending execution controls.

Stability protocols generate scheduled pulls and retain acceptance, reserve and retention evidence. Released lot rows and their scientific evidence remain immutable. New stability testing on a released lot therefore uses controlled external evidence links; do not reopen a released lot to fit a pull into the quarantine testing workflow. Retention obligations preserve their anchors and calculation basis; missing anchors or active holds block disposal eligibility.

Native reports resolve the exact assignment ID, lot and payload hash captured by signed disposition, verify the payload digest, and take specification and method evidence only from that frozen assignment. Missing or unverifiable evidence holds issuance; live requirement collectors cannot replace it. Holds remain live until signing, including holds placed after lot release. Issuance rechecks the reviewed evidence hash and authority under lock; a stale preview requires renewed review, without a separate persistent draft-snapshot workflow. WeasyPrint renders only the frozen snapshot with external resource fetching denied. Snapshot, version, issued PDF bytes/checksum and amendment linkage are stored in PostgreSQL in the signing transaction; a rendering failure rolls back issuance. Downloads verify and return stored bytes rather than regenerating from current records. An amendment adds a version and retains the original. Source instrument files and future uploads still need a deliberate durable-storage design; Render's ephemeral filesystem is not that store.

## Operation and deployment

| Item | Contract |
|---|---|
| Local database | Compose PostgreSQL 17 on loopback port 55433 |
| Render web | `openbga-qualab`, Docker, 1c-2g, Virginia, automatic deployment off |
| Render database | `openbga-qualab-db`, PostgreSQL 17, 0.5c-1g, 5 GB, private access; database name/user `open_qual` |
| Migration | Fresh project history; serialized pre-deploy `python manage.py migrate --noinput` |
| Health | `/health/` process health; `/ready/` checks database availability |
| Source offer | Every page footer links to `SOURCE_CODE_URL` (default <https://github.com/openbga/qualab>) for AGPL-3.0 section 13 |
| Static | Vendored local assets; `collectstatic` during build and before template tests |
| Security | Production secret/hosts/origins from environment, HTTPS, secure cookies and CSRF |
| Time | UTC default; retain unambiguous timestamp/zone context; never reinterpret signed records |

Resource sizes above are user-authorized configuration, not a claim of deployment or current provider pricing. Secrets and operational evidence stay out of Git. Seeding is deliberate and never part of deploy. Use backward-compatible migrations when instances overlap; reverting code does not revert schema. Restore into an isolated database and verify audit/signature/record relationships before relying on recovery. Production requires an owner for backup retention, restore rehearsal, access reviews, identity proofing and intended-use validation.

## Integration gate

The integrated development candidate passed the combined gate on 2026-11-10: 497 PostgreSQL tests passed (one optional artifact-export test skipped), eight headless browser checks passed (including refused transitions and idle/absolute session expiry), and the production container smoke and bounded synthetic restore rehearsal passed. This evidence does not cover every configured workflow or operational acceptance. Run Ruff, PostgreSQL pytest, Django checks, migration drift checks and collectstatic. Contract tests prioritize denied/self-review actions, effective rules, stale revisions, PIN failure/lockout, atomic rollback, immutability and failed/incomplete disposition. Run a native headless synthetic journey through approved specifications, sampling, batch QC, independent review, disposition and PDF issuance/amendment with distinct actors. Exercise OOS/retest and unsupported-requirement holds, and inspect keyboard access, error behavior and PDF output. The DEBUG-only `seed_demo --journey` remains a smaller foundation demonstration; it is not evidence of native journey acceptance. The integrator owns shared files and runs the combined gate once after independent packages pass focused checks. Passing development tests is not regulated-system validation.
