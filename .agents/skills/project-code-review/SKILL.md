---
name: project-code-review
description: The pre-PR quality gate for OpenBGA QM LIMS. It reviews the current diff against AGENTS.md (server-side authorization, signature + audit + state committed together, no self-review across roles, PIN secrecy, immutable revisions and issued certificate bytes, exact Decimal values), the frontend rules and ui-standards, migrations, tests, the traceability map and validation pack, page documentation, the roadmap and product status, and the wording rules; fixes what it finds in place; runs the CI checks plus the affected pytest and browser journeys; captures before/after screenshots for UI changes; and ends with a summary table. Use it whenever you finish a change and before you commit, push or open a pull request, and whenever someone asks to review, check or verify the work on a branch.
---

# Pre-PR review and gate

This is a gate, not a report: fix what you find, rerun what you changed, and report only what
cannot be fixed safely. Keep the review to the diff; untouched legacy code is out of scope unless
the change makes it wrong.

## 0. Scope the diff

```sh
git fetch origin develop -q
git diff --name-only origin/develop...HEAD   # committed on this branch
git status --short                            # plus uncommitted and untracked work
```

Sort the files into groups; each check below names the group it applies to:

| Group | Paths |
| --- | --- |
| Python domain and views | `*/models.py`, `*/services.py`, `*/views*.py`, `*/forms.py`, `core/*.py`, `accounts/*.py`, other app `*.py` |
| Migrations | `*/migrations/*.py` |
| Templates and front end | `templates/**`, `*/templates/**`, `static/css/**`, `static/js/**`, `*/static/**` |
| Certificate and exports | `reporting/render.py`, `reporting/lot_record.py`, `reporting/templates/reporting/pdf/**`, `reporting/templates/reporting/_certificate.html` |
| Tests | `tests/**`, `*/tests/**`, `e2e/**` |
| Docs | `docs/**`, `docs/pages/**`, `website/**`, `README.md`, `CONTRIBUTING.md` |

If the diff is empty, say "Nothing to review" and stop. Ignore `.local/`. Never edit `LICENSE` or
`static/vendor/**`. An agent working under a coordinator runs no Git command that writes
(AGENTS.md rule 7).

## 1. Domain and authorization (Python changes)

Read each changed function with its callers, against `.agents/rules/backend.md`, which names the
helpers to reuse (`core.services.require_role`, `sign_transition`, `verify_pin`, `set_pin`,
`core.audit.record_event`, `supersede`, `catalog.units`, `core.formulas`, `core/lookups.py`).
Code that reimplements one of them is a finding. Fix in place:

| # | Check | What to look for | Fix |
| --- | --- | --- | --- |
| 1 | Authorization on the server (rule 3) | A view, export, download, fragment or lookup queryset without `require_role`; a check only in the template or menu; admin or superuser treated as scientific authority | `require_role` in the service and view; test the refused role |
| 2 | Signature, audit and state together (rules 3–4) | A transition outside `sign_transition`; a state change, `ElectronicSignature` and `AuditEvent` in separate transactions; preconditions checked before the lock and not rechecked in `apply`; no `expected_revision` | One `sign_transition(..., expected_revision=…, apply=…)`; preconditions inside `apply`; stale-revision test |
| 3 | No self-review (rule 3) | Review, disposition, rejection, acceptance or issue without excluding everyone who authored the evidence, including a user holding several roles | Reuse the module's independence check; test the author with the deciding role |
| 4 | PIN secrecy (rule 5) | A PIN in a log, message, audit `before/after`, snapshot, exception or template value; `verify_pin` inside an enclosing transaction (failed counters would roll back); a PIN field prefilled; missing `@sensitive_variables` | `verify_pin` outside the transaction, `@sensitive_variables`, never store or echo; test that a wrong PIN is counted even when the action is refused |
| 5 | Originals kept (rule 4) | Editing an approved rule, specification or method revision, an observation, a signed record or an append-only history row; deleting evidence | `supersede` / a linked correction record; database guard triggers stay intact |
| 6 | Certificates are stored bytes | Re-rendering an issued PDF, editing a `ReportVersion`, an amendment that changes the original; a renderer that fetches anything beyond `reporting/render.py`'s allowlist | New version with `amends_version`; serve `read_pdf` bytes; keep the exact-URL fetcher |
| 7 | Exact numbers | `float(`, `round(`, a `FloatField` or float arithmetic on results, limits or quantities; formatting that drops the entered digits | `Decimal`; `catalog.units.rounded` / `plain`; `core.formulas.calculate` |
| 8 | Concurrency | Read-modify-write without `select_for_update` or a revision check | Lock, recheck `expected_revision`, clear stale-edit message |
| 9 | No invented policy or claims (rule 6) | New thresholds, acceptance rules or regulatory statements without a primary source in `docs/regulations.md`; "compliant", "validated", "certified" wording; a segment preset presented as law | Make it configuration or remove it; flag it for the owner |
| 10 | Names and data (AGENTS.md, rule 10) | Another LIMS/LIS/middleware product or vendor named anywhere; real names, customers, credentials, dumps or runtime output in code, fixtures, docs or screenshots | Remove; synthetic values only (`LOT-TEST-001`, `analyst.test`) |
| 11 | Printed certificate text | A new or changed sentence on the certificate of analysis | Leave it out and list it for owner approval |

## 2. Migrations

- Additive and backward compatible; never edit a merged migration; immutable-history triggers
  stay in place.
- `uv run python manage.py makemigrations --check --dry-run` says "No changes detected" against
  PostgreSQL (never SQLite).
- A data migration is reversible or says why, and never rewrites signed or issued records.

## 3. Templates and front end (follow `build-page` and `.agents/rules/frontend.md`)

| # | Check | Fix |
| --- | --- | --- |
| 12 | Built from `{% load ui %}` components; no copied component markup; no `{% include %}` of `templates/includes/`; a page's own partial included with `only` | Use the tag; add a parameter to the component |
| 13 | Tokens only: no inline style, `<style>`, colour literal, raw px/rem, unthemed colour utility; muted is `.vr-muted` | A `--vr-*` token or class |
| 14 | Icons only through `{% icon %}` / `vrUi.icon`, Bootstrap Icons symbols in the sprite | Copy the symbol into `static/img/icons.svg` |
| 15 | Controls through form widgets; large model lists use `RemoteSelect` with an authorized lookup | Render the field; register the lookup |
| 16 | Page type: one primary (last), ≤3 secondaries + More, identifier row links, list states, breadcrumbs only where due, `page_title` from the view | `docs/ui-standards.md` |
| 17 | Must-see QC facts (status, holds, OOS, open investigations, awaiting review, amendments) in `page_meta` or a notice; text or glyph with every colour | Move them up; add the cue |
| 18 | Panels own spacing; no utilities inside panel bodies; no panel in a panel | `panel_section`, `table=True` |
| 19 | Signing only on sign pages through `signature_card` and the signature dialog, never the form dialog; an unavailable action explained before any PIN is asked | `core/form_surfaces.py` lists data-entry pages only |
| 20 | Wording: sentence case, `New`/`Record`/`Change`/`Correct`/`Cancel`, one term per concept, same words as sidebar and title | Rename |

## 4. Tests, traceability, docs

- New or changed behaviour has tests beside the app's existing ones: the allowed and the refused
  role, self-review across roles, a stale revision, a wrong or locked PIN that is still counted,
  the audit event, and exact values. Fix the code, not the test. A test that guards a gate or
  evidence (release, signatures, review, audit, disposition, certificate, acceptance) is never
  loosened; markup changes read stable `data-*` hooks.
- Every new test module is traced in `docs/traceability.toml` under its requirement or
  `[project]`; a test that may skip in CI needs a `[skips]` reason. A new requirement in
  `docs/product.md` has at least one traced test. `tests/test_validation_pack.py` refuses an
  incomplete map.
- Any page or named-URL change updates `docs/pages/` in the same change with the `document-page`
  skill and sets `reviewed` (rule 12). Non-page routes go in `pagedocs/coverage.py` exemptions with
  a reason.
- A change that completes or re-scopes a capability area updates `website/roadmap.html` and the
  status tables in `docs/product.md` (rule 13).
- Third-party files carry a licence file and a `THIRD_PARTY_NOTICES.md` row; the `LICENSE`, the
  `NOTICE` and the footer **Source code** link stay as they are.

## 5. Run the gate

The same commands as `.github/workflows/checks.yml`, with your own test database:

```sh
set -a; . ./.env; set +a
uv run ruff check . && uv run ruff format --check .
uv run python manage.py check
uv run python manage.py makemigrations --check --dry-run
uv run python manage.py collectstatic --noinput
TEST_DATABASE_NAME=test_open_qual_<you> uv run pytest <affected paths> -q
```

Affected paths: the changed apps' `tests/`, `pagedocs`, and the `tests/test_*.py` covering the
change (`test_ui_standards`, `test_css_tokens`, `test_include_isolation`, `test_controls`,
`test_icons`, `test_form_dialog`, `test_lookups`, `test_preferences` for template or front-end
changes; `test_validation_pack` when tests or the map changed). Run the full
`uv run pytest -n auto` when shared code (`core/`, `accounts/`, `templates/includes/`,
`templates/layouts/`, `static/css/app.css`, settings) or a migration changed. Rerun a failing test
once by itself before calling it flaky.

When templates, `static/js` or `static/css` changed, run the browser journeys that open those
pages plus the layout checks, headless only:

```sh
uv run --group e2e python manage.py collectstatic --noinput
grep -ln "<url path or route>" e2e/test_*.py        # journeys that visit the changed pages
TEST_DATABASE_NAME=test_open_qual_e2e_<you> uv run --group e2e pytest -c e2e/pytest.ini \
  e2e/<affected journeys>.py e2e/test_panel_spacing.py e2e/test_alignment.py e2e/test_shell_layout.py
```

Certificate changes also run `reporting/tests` (pdftotext must be installed) and look at the PDFs
written with `OQ_PDF_OUT=<dir>` (`test_write_review_pdfs`, `test_write_certificate_review_pdfs`).

## 6. Before / after screenshots (any visible change)

The dev server runs on http://127.0.0.1:8010 with demo data and `DEMO_PASSWORD` in `.env`:

```sh
set -a; . ./.env; set +a
uv run --group e2e python scripts/ui_compare/capture.py --list
uv run --group e2e python scripts/ui_compare/capture.py --pages <id>,/path/,demo_quality:/path/
```

- "After" is the running dev server (`--after URL` to change it). "Before" is a temporary
  worktree of `origin/develop` served on 127.0.0.1:8013 (`--before-port`), removed at the end; it
  reads the same database and refuses non-additive migrations (`--before-database-url` for a
  copy).
- `--pages` takes ids from `--list`, `/path/` (signed in as `demo_admin`) or
  `demo_<role>:/path/`. `--after-only` reuses earlier "before" shots. Pick every page the diff
  changes.
- Output: `.local/ui-compare/index.html`, `shots/` (light and dark), `manifest.json`; optional
  notes in `.local/ui-compare/notes.json`, rebuilt with `python3 scripts/ui_compare/build.py`. The
  run exits non-zero if a page could not be captured. Details: `scripts/ui_compare/README.md`.
- Attach the relevant pairs (light and dark) to the pull request under "Before / after". Never
  commit screenshots; synthetic data only.

## 7. Summary

End with this table, then anything that needs a human:

```markdown
## Review summary

| Area | Result | Notes |
| --- | --- | --- |
| Scope | N files (Python, templates, migrations, tests, docs) | |
| Domain, authorization, signing | Pass / Fixed N | file:line, what changed |
| Migrations | None / Additive, check clean | |
| Templates and UI rules | Pass / Fixed N | |
| Tests and traceability | Added / Not needed (why); map complete | |
| Page docs, roadmap, product status | Updated / Not needed | |
| Wording, names, compliance claims | Pass / Fixed N | |
| ruff, format, check, makemigrations, collectstatic | Pass | |
| pytest (paths) | N passed | failures and their owner if not yours |
| Browser journeys and layout checks | N passed / Not run (no UI change) | |
| Screenshots | .local/ui-compare/index.html / Not needed | |

### Needs a human
- Policy or behaviour decisions, new certificate wording, failures outside this diff, anything
  not fixed and why.
```

Flag rather than auto-fix a change that would alter behaviour, a public URL, certificate output
or stored data, and say so explicitly when the diff touches authorization, signing, stored
history, a migration or certificate output: the pull request template asks reviewers to look
there.
