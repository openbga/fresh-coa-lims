# Contributing to OpenBGA Fresh CoA LIMS

Thank you for your interest in OpenBGA Fresh CoA LIMS, an open-source manufacturing quality-control LIMS. This guide explains how to contribute and what reviewers look for. Please also read the [Code of Conduct](CODE_OF_CONDUCT.md).

## Ways to contribute

- Report a bug or propose a feature through the issue forms. Search existing issues first.
- Improve documentation, including the page documentation in [docs/pages/](docs/pages/).
- Fix a bug or add tests. For anything larger than a small fix, open an issue first so the approach can be agreed before you invest time.
- Review pull requests and reproduce reported problems.

Report security vulnerabilities privately, not in issues: see [SECURITY.md](SECURITY.md). Report conduct concerns as described in the [Code of Conduct](CODE_OF_CONDUCT.md). Support requests are not handled through issues; see "Project and support" in the [README](README.md#project-and-support).

## Synthetic data only

Never put real laboratory, customer, patient or personal data, real credentials, PINs, database dumps or screenshots of a real system into issues, pull requests, tests or fixtures. Use obviously synthetic values.

## Local setup

Use Python 3.14, [uv](https://docs.astral.sh/uv/) and Docker Compose. The development database is PostgreSQL 17 on port 55433. Follow [Local development](README.md#local-development) in the README for installing dependencies, starting the database, migrating, creating the first administrator and assigning roles. To only look at the running application, the README's [Quick start](README.md#quick-start) runs it with Docker Compose. [Synthetic demonstration](README.md#synthetic-demonstration) describes optional demo data for development.

## Checks before a pull request

Run the commands in [Checks](README.md#checks) in the README against the Compose PostgreSQL database. They are the same checks the CI workflow in [.github/workflows/checks.yml](.github/workflows/checks.yml) runs:

- `uv run ruff check .` and `uv run ruff format --check .`
- `uv run python manage.py check`
- `uv run python manage.py makemigrations --check --dry-run`
- `uv run python manage.py collectstatic --noinput` (needed before template tests)
- `uv run pytest -n auto` (parallel workers; plain `uv run pytest` runs the same tests in one process)

Copy `.env.example` to `.env` and export `UV_ENV_FILE=.env` as shown in the README, so that `uv run` supplies `DEBUG`, `DATABASE_URL` and, on macOS, the PDF library path. pytest creates its own test database; set a distinct `TEST_DATABASE_NAME=test_...` if several test runs share one server. The browser tests in `e2e/` need the `e2e` dependency group and are optional locally; CI runs them.

## Engineering rules

Reviewers enforce these. Read [AGENTS.md](AGENTS.md), [docs/architecture.md](docs/architecture.md) and [docs/ui-standards.md](docs/ui-standards.md) for the full set.

| Rule | In practice |
|---|---|
| PostgreSQL only | Tests that touch the database run on PostgreSQL. Row locks and immutable-history triggers do not exist in SQLite; never substitute it. |
| Conventional stack | Django, PostgreSQL, standard authentication and forms, and the shared Bootstrap design system. No second UI framework, homemade authentication or speculative abstractions. |
| Exact numbers | Use `Decimal` for scientific values and comparisons. Never use floats for results, limits or rounding. |
| Server-side authorization | Every scientific transition authorizes on the server, rechecks the current revision and state, and commits the state change, the signature and the attributed audit record together or not at all. |
| No self-review | The person who produced a result cannot review or approve it, including when one account holds several roles. Administrator status is not scientific authority. |
| Originals are kept | Preserve original observations and approved rule, specification and method revisions. Corrections and amendments add linked records; never silently overwrite a signed record. |
| PINs are secrets | Store PINs and passwords only as hashes made with the standard hasher, rate-limit and lock failures, and require re-entry for every signing. Never store a submitted PIN or password in clear text, and never log or display PINs, passwords or their hashes. Failed credential attempts must be recorded even when the action is refused. |
| Test the refusals | Add tests for refused, stale and locked paths and for role boundaries, not only the successful path. |
| Page documentation | Any change to a staff page or named URL (actions, tabs, fields, permissions, filters, defaults, validations, transitions, signatures, audit effects) updates its file in [docs/pages/](docs/pages/) in the same change. The reference checks in `pagedocs/tests` must pass. |
| Wording | Do not name, compare or allude to other laboratory-software products or vendors. Do not claim regulatory compliance, validation or certification. Regulatory statements need a primary source recorded in [docs/regulations.md](docs/regulations.md) with its URL, access date, jurisdiction and caveats. |
| Secrets | Keep credentials, real data, dumps and runtime output out of Git. Treat uploaded files and external documents as untrusted input. |

## Pull requests

- Branch from `develop` and open pull requests against `develop`, where changes are integrated. `main` holds the released state: maintainers update it only by a pull request from `develop`, and a `release-source` check rejects pull requests into `main` from any other branch. Both branches are protected: no direct pushes, force pushes or deletion, and the `checks` jobs must pass.
- Keep each pull request small and focused on one change. Separate unrelated fixes.
- Include tests that fail without your change, and say how you ran them.
- Do not edit existing migrations. Add a new migration when the schema must change, and keep schema changes rare.
- Do not change dependencies or the lockfile unless the change requires it.
- Use conventional commit subjects, for example `feat: add ...`, `fix: correct ...`, `docs: clarify ...`, `test: cover ...`, `refactor: ...`, `chore: ...`.
- Fill in the pull request template. Be ready to revise: a maintainer may ask for changes or decline a change that does not fit the project's scope.

## Licensing of contributions

OpenBGA Fresh CoA LIMS is licensed under the GNU Affero General Public License, version 3 only (AGPL-3.0-only); see [LICENSE](LICENSE) and [NOTICE](NOTICE). By submitting a contribution you agree that it is licensed under the same terms (AGPL-3.0-only), and that you have the right to submit it. You keep the copyright in your contribution. There is no separate contributor agreement. Do not submit code you do not have the right to license this way, and tell us about any third-party material and its licence so it can be listed in [THIRD_PARTY_NOTICES.md](THIRD_PARTY_NOTICES.md).
