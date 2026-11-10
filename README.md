# Open Qual IQ

A manufacturing quality-control LIMS for pharma/biotech, supplements, food, chemicals and devices. One shared workflow uses versioned configuration, independent review, PIN signatures and audit history. Built with Django, PostgreSQL and locally served Bootstrap/HTMX assets.

The implemented workflow covers approved methods/specifications and sampling assignments → lot/sample → numeric observations, replicates and batch QC → OOS/retest where needed → independent signed review → QC disposition → immutable PDF CoA and amendments. Laboratory resource records, qualification authorization, stability protocols/pulls, reserves, retention obligations and holds are also implemented. The integrated development candidate passed its combined gate on 2026-11-10; this is not a completed MVP or production validation. Use synthetic data only; no regulatory compliance is claimed.

| Implemented boundary | Current limit |
|---|---|
| Native analytical testing | Numeric results with inclusive limits; approved precision rounds half-up, null precision compares the exact mean. Nonterminating or more-than-eight-decimal exact means fail submission; qualitative/exclusive requirements remain held |
| Laboratory operations | Method-specific analyst qualification gates native observations/corrections; equipment/reagent selection and use remain a separate explicit authorization workflow |
| Stability | Protocols, scheduled pulls, acceptance and controlled evidence links; testing of released lots uses external evidence because released lot records remain immutable |
| Reporting | Signed issuance/amendments with stored PDF bytes, snapshots and checksums; manufacturer batch release remains a separate decision |

| Read | Purpose |
|---|---|
| [Product](docs/product.md) | Scope, roles, journeys and requirement IDs traced to research |
| [Architecture](docs/architecture.md) | Shared integrity contracts and operational boundaries |
| [Operations](docs/operations.md) | Backup/restore, manual deployment and identity/signing procedures |
| [UI standards](docs/ui-standards.md) | Components, accessibility and signing interaction |
| [Research](docs/research/regulations.md) | Dated regulatory matrix, sources and applicability caveats |
| [Reuse](docs/research/reuse.md) | Open Roots IQ provenance and reuse decisions |
| [Working instructions](AGENTS.md) | Contributor constraints and verification |

## Local development

Use Python 3.14, uv and Docker Compose. The PostgreSQL port is **55433**, separate from Open Roots IQ's 55432. The example database credentials are local-only. Settings read environment variables; copying `.env.example` alone does not load them.

```sh
uv sync --frozen
export DEBUG=true
export DATABASE_URL=postgresql://open_qual:open_qual@127.0.0.1:55433/open_qual
docker compose up -d db
uv run python manage.py migrate
uv run python manage.py collectstatic --noinput
uv run python manage.py createsuperuser --username admin
uv run python manage.py assign_roles admin admin --actor admin --reason 'Initial synthetic instance setup'
uv run python manage.py runserver 127.0.0.1:8000
```

Sign in at <http://127.0.0.1:8000/accounts/login/>. There is no public signup. Django admin is read-only for identity maintenance; role changes use the audited `assign_roles` command. It replaces the complete role set; passing no roles revokes all laboratory roles. A superuser does not automatically hold scientific roles.

```sh
uv run python manage.py create_staff analyst analyst --actor admin --reason 'Synthetic analyst setup'
uv run python manage.py create_staff reviewer reviewer --actor admin --reason 'Synthetic reviewer setup'
uv run python manage.py create_staff quality quality --actor admin --reason 'Synthetic quality setup'
```

The audited `create_staff` command prompts privately for a validated password. Use distinct synthetic actors for analyst, reviewer and quality. Each signer enrolls their own PIN at `/signature-pin/` by confirming their login password. PINs contain 8–32 digits; five failed attempts lock signing for 15 minutes. Never put passwords or PINs into source files or command-line arguments.

For manual configuration, run `uv run python manage.py seed_rules --actor admin`. The five seeded segment presets remain **drafts**. They are synthetic identity-test examples, not complete segment policies. A quality actor other than the author must inspect and sign approval before a rule can be used. Approved intervals must have a finite end; schedule non-overlapping replacement revisions before expiry. No automatic retirement or retroactive editing of approved rules is provided. The rule schema accepts required test codes and supported review/disposition meanings. The catalog adds independently approved method/specification revisions, method QC policies and sampling plans; lot assignments preserve their applicability and revision snapshots. Broader market/obligation resolution still needs an approved local policy.

For native work, receive a lot under an approved effective rule, assign approved specifications and a sampling plan, record sampling provenance, and assign its required tests. Record observations against the frozen requirements, complete the configured replicates/batch QC and submit for independent review. OOS investigations preserve original data and require controlled assessment, retest/resample authorization and conclusion. Quality disposition checks assigned requirements, analytical completeness/review/investigations, independence and active holds before signing. A released lot can then receive a signed, versioned CoA.

Requirements cannot be reassigned once native tests exist. New QC batches use only currently effective approved method revisions; an older frozen test revision cannot be moved into a newer-method batch or create a new old-method batch. This intentionally holds that work until a controlled resolution exists.

Manual foundation results with analyst-entered limits are available only in `DEBUG` on lots without native assignments. Production disposition requires the assigned-specification path; mixing foundation and native evidence is blocked. This development fallback is not a production workflow.

## Synthetic demonstration

On a fresh development database, after provisioning the bootstrap administrator, run `DEBUG=true uv run python manage.py seed_demo --actor admin --journey` **instead of** manually running `seed_rules` first.
The command privately prompts for synthetic credentials (or reads `DEMO_PASSWORD` and `DEMO_PIN` from the environment), creates five `demo_<role>` users, draft segment rules and draft catalog/sampling profiles. With `--journey`, it also approves an illustrative chemical rule and creates a foundation result awaiting independent review.
It refuses production mode and non-demo name collisions, including pre-existing rule presets, and never resets existing credentials on rerun. Use `demo_reviewer` and `demo_quality` in separate login sessions to finish this minimal development journey. Omit `--journey` to leave all presets as drafts. Catalog/specification/sampling drafts still need an independent quality approver; the seed is not a fully approved native workflow or a validated test panel. Do not seed on deployment.

## Checks

Run against the Compose PostgreSQL database. pytest creates a separate test database; the local database role must be able to create it. Use a distinct `TEST_DATABASE_NAME=test_...` when another session is testing.

```sh
export DEBUG=true
export DATABASE_URL=postgresql://open_qual:open_qual@127.0.0.1:55433/open_qual
uv run ruff check .
uv run python manage.py check
uv run python manage.py makemigrations --check --dry-run
uv run python manage.py collectstatic --noinput
uv run pytest
```

PostgreSQL is required for row locks and immutable-history triggers; SQLite is not a substitute. Headless browser tooling is in the `e2e` dependency group (`uv sync --group e2e`, then `uv run playwright install --only-shell chromium`). Use an isolated synthetic database/server for browser work. Verification results and local work-package ownership are recorded in the coordinator handoff and `.local/plan/work-packages.md`.

## Deployment

`Dockerfile`, CI and `render.yaml` define the foundation. The authorized Blueprint describes `open-qual-iq` (Docker, 1c-2g, Virginia) and `open-qual-iq-db` (PostgreSQL 17, 0.5c-1g, 5 GB), with automatic deployment off. It runs migrations in pre-deploy and checks `/health/`; `/ready/` also checks the database. Resource definition does not mean deployment has occurred. Provision only after the integrated checks pass.

Production requires a unique `SECRET_KEY`, correct hosts/trusted origins, HTTPS and controlled account setup. Never enable `DEBUG` on a public instance. Do not seed or reset data during normal deploy. Identity proofing, MFA/session policy, PIN recovery, appropriate signature-component validation, backups/restores, retention and intended-use validation remain operational work before regulated use. HTTP signing requires typed username and PIN each time; controlled sessions expire after 15 minutes idle or 8 hours total by default. MFA and deployment-specific identity/component validation remain outstanding. Issued PDF bytes are stored with their immutable versions in PostgreSQL. Render's filesystem is ephemeral; future instrument files or other uploads need controlled durable storage.

## License and provenance

GPL-3.0-only; see [LICENSE](LICENSE) and [third-party notices](THIRD_PARTY_NOTICES.md). Derived from selected Open Roots IQ platform/design assets and patterns, source baseline `d04a916`, with fresh migrations and manufacturing-specific contracts. No reference repository credentials, runtime data or environmental rule presets are included. Retain original license and dependency notices when distributing.
