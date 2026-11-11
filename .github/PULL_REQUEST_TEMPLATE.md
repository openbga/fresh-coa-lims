## Summary

What does this change do, and why? Link the issue it addresses, if any.

## Checks

- [ ] This pull request targets `develop`
- [ ] `uv run ruff check .` and `uv run ruff format --check .` pass
- [ ] `uv run python manage.py check` and `uv run python manage.py makemigrations --check --dry-run` pass
- [ ] `uv run pytest` passes on PostgreSQL (and `collectstatic` was run first)
- [ ] New tests cover the change, including refused, stale or locked paths and role boundaries where relevant
- [ ] Scientific transitions authorize on the server and commit state, signature and audit together; no self-review
- [ ] Original records are not overwritten; corrections add linked records
- [ ] PINs and passwords are stored only as hashes; PINs, passwords and hashes are never logged or shown
- [ ] `docs/pages/` is updated for any changed staff page or named URL
- [ ] Only synthetic data is used; no real laboratory, customer or personal data
- [ ] No other-product names and no claim of regulatory compliance or validation
- [ ] The commit subjects are conventional (`feat:`, `fix:`, `docs:`, ...)
- [ ] I agree that this contribution is licensed under AGPL-3.0-only

## Notes for reviewers

Anything that needs a decision, a migration, a dependency change or a follow-up.
