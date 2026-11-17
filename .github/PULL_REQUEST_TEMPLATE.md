## Summary

What does this change do, and why? Link the issue it addresses, if any.

## How it was verified

Commands you ran and what you checked by hand (journeys, roles, refused paths, light and dark).

## Before / after

For visible changes: before (`develop`) and after (this branch) screenshots of synthetic data, light and dark, from `scripts/ui_compare/capture.py`. Delete this section when nothing visible changed.

## Checks

- [ ] This pull request targets `develop`
- [ ] Ran the `project-code-review` skill (or its checks by hand) and fixed what it found
- [ ] `uv run ruff check .` and `uv run ruff format --check .` pass
- [ ] `uv run python manage.py check` and `uv run python manage.py makemigrations --check --dry-run` pass
- [ ] `uv run pytest -n auto` passes on PostgreSQL (and `collectstatic` was run first)
- [ ] New tests cover the change, including refused, stale or locked paths and role boundaries where relevant
- [ ] New tests are traced in `docs/traceability.toml` under their requirement or `[project]`
- [ ] Scientific transitions authorize on the server and commit state, signature and audit together; no self-review
- [ ] Original records are not overwritten; corrections add linked records
- [ ] PINs and passwords are stored only as hashes; PINs, passwords and hashes are never logged or shown
- [ ] `docs/pages/` is updated for any changed staff page or named URL
- [ ] An entry in `changelog.d/` describes each change users, deployers or integrators can observe, and `CHANGELOG.md` is regenerated (`uv run python manage.py changelog`); otherwise the summary says there is no observable change
- [ ] Only synthetic data is used; no real laboratory, customer or personal data
- [ ] No other-product names and no claim of regulatory compliance or validation
- [ ] The commit subjects are conventional (`feat:`, `fix:`, `docs:`, ...)
- [ ] I agree that this contribution is licensed under AGPL-3.0-only

## Notes for reviewers

Anything that needs a decision, a migration, a dependency change or a follow-up.
