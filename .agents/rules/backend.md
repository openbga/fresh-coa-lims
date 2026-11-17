---
paths:
  - "*/models.py"
  - "*/views*.py"
  - "*/services*.py"
  - "*/forms*.py"
  - "*/migrations/**"
  - "*/management/**"
  - "core/**"
  - "accounts/**"
  - "config/**"
  - "docs/traceability.toml"
---

# Backend rules

The principles are in `AGENTS.md` (rules 2–5, 9) and `docs/architecture.md`. This file names the
code that implements them. Reuse it; don't write a second version.

- **Who may act.** `core.services.require_role(actor, *roles)` checks an active account and its
  explicit role groups. Call it inside the service, not only in the view; a hidden button, menu
  visibility or admin status is never the gate. Views add `login_required` and
  `require_http_methods`.
- **No self-review.** The service compares the producer with the actor under the record lock
  (for example `quality/services.py` `review_result`: "You cannot review your own result.").
  Holding several roles never lifts it.
- **Signed transitions.** Use `core.services.sign_transition(actor=, pin=, obj=, expected_revision=,
  meaning=, reason=, permission=, apply=, prepare=)`. It verifies the PIN, locks the signer and the
  record, rejects a stale `revision`, runs `apply`, increments `revision` and commits the state, the
  `ElectronicSignature` and the audit event together. Put state preconditions in `apply` so they
  are rechecked under the lock. Never write a signature or audit row by hand around it.
- **PINs.** `verify_pin` must run outside any enclosing transaction (it raises otherwise) so
  failed-attempt counters and `signature.denied` events survive a refused action. Mark functions
  that touch a PIN with `@sensitive_variables`; set PINs only through `set_pin`. Never log, store,
  echo or snapshot a PIN, password or hash; `core.audit.snapshot` is never used on credential or
  account models.
- **Audit.** `core.audit.record_event(actor=, action=, obj=, before=, after=, reason=)` must share
  the domain transaction (it raises otherwise). Unsigned edits still lock the row, recheck
  `expected_revision` and record an event.
- **Originals are kept.** Approved rule, specification and method revisions are superseded, not
  edited (`core.services.supersede`, `catalog/migrations/0006_supersession.py`); evidence tables are
  guarded by database triggers (`analytical/migrations/0002_evidence_guards.py`). Corrections and
  report amendments add linked records.
- **Exact numbers.** `Decimal` only for results, limits and rounding. Use
  `catalog.units.rounded` / `plain` and `core.formulas.calculate` (half-up to the approved
  decimals); never `float`.
- **Migrations.** Never edit a merged migration; keep `makemigrations --check --dry-run` clean on
  PostgreSQL.
- **Tests and traceability.** Cover the allowed and refused role, self-review, the stale revision,
  a wrong or locked PIN and the audit event, on PostgreSQL. Trace every new test module in
  `docs/traceability.toml` under its requirement or `[project]`; `tests/test_validation_pack.py`
  refuses an incomplete map.
