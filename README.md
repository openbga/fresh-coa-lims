# Open Qual IQ

A manufacturing quality-control LIMS foundation for pharma/biotech, supplements, food, chemicals and devices. One shared workflow uses versioned configuration, independent review, PIN signatures and audit history. Built with Django, PostgreSQL and locally served Bootstrap/HTMX assets.

This phase provides the platform and a thin lot → sample → result → signed review → signed QC disposition journey. Full specifications, worksheets/QC, OOS investigations, stability, equipment/training gates and immutable CoA reporting remain planned work. Synthetic demonstration data only. The software does not claim regulatory compliance or production validation.

| Read | Purpose |
|---|---|
| [Product](docs/product.md) | Scope, roles, journeys and requirement IDs traced to research |
| [Architecture](docs/architecture.md) | Shared integrity contracts and operational boundaries |
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
uv run python manage.py seed_rules --actor admin
uv run python manage.py runserver 127.0.0.1:8000
```

Sign in at <http://127.0.0.1:8000/accounts/login/>. There is no public signup. Django admin is read-only for identity maintenance; role changes use the audited `assign_roles` command. It replaces the complete role set; passing no roles revokes all laboratory roles. A superuser does not automatically hold scientific roles.

```sh
uv run python manage.py create_staff analyst analyst --actor admin --reason 'Synthetic analyst setup'
uv run python manage.py create_staff reviewer reviewer --actor admin --reason 'Synthetic reviewer setup'
uv run python manage.py create_staff quality quality --actor admin --reason 'Synthetic quality setup'
```

The audited `create_staff` command prompts privately for a validated password. Use distinct synthetic actors for analyst, reviewer and quality. Each signer enrolls their own PIN at `/signature-pin/` by confirming their login password. PINs contain 8–32 digits; five failed attempts lock signing for 15 minutes. Never put passwords or PINs into source files or command-line arguments.

The five seeded segment presets remain **drafts**. They are synthetic identity-test examples, not complete segment policies. A quality actor other than the author must inspect and sign approval before a rule can be used. Approved intervals must have a finite end; schedule non-overlapping replacement revisions before expiry. No automatic retirement or retroactive editing of approved rules is provided. The current rule schema accepts required test codes and the supported review/disposition meanings; richer applicability, limits and obligations belong to the planned catalog work.

With an approved effective rule, the analyst receives a lot, adds its sample and records each required test with value, unit and limits. A separate reviewer signs conforming results. Quality then signs QC disposition after completeness and independent-review checks. Failed or incomplete results remain blocked; the full investigation/correction workflow is pending. This foundation's limits are entered for the synthetic test and are not yet backed by an approved specification catalog.

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

Production requires a unique `SECRET_KEY`, correct hosts/trusted origins, HTTPS and controlled account setup. Never enable `DEBUG` on a public instance. Do not seed or reset data during normal deploy. Identity proofing, MFA/session policy, PIN recovery, appropriate signature-component validation, backups/restores, retention and intended-use validation remain operational work before regulated use. The foundation does not yet provide MFA or demonstrate all Part 11 signing-session requirements. Render's filesystem is ephemeral; future persistent documents need controlled durable storage.

## License and provenance

GPL-3.0-only; see [LICENSE](LICENSE) and [third-party notices](THIRD_PARTY_NOTICES.md). Derived from selected Open Roots IQ platform/design assets and patterns, source baseline `d04a916`, with fresh migrations and manufacturing-specific contracts. No reference repository credentials, runtime data or environmental rule presets are included. Retain original license and dependency notices when distributing.
