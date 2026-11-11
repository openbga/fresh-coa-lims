# OpenBGA Qual

The product name is **OpenBGA Qual** and the repository is [openbga/qual](https://github.com/openbga/qual), under the **OpenBGA** organization. Use this name in the application, presentation website and documentation. The support notice is: "Are you looking for support? Contact [bgasoft.com](https://bgasoft.com)."

Read `docs/product.md`, `docs/architecture.md`, `docs/ui-standards.md` and relevant source/tests. Regulatory applicability, sources and caveats are in `docs/regulations.md`. Keep documentation for intent and constraints, not a duplicate implementation description.

One manufacturing QC system serves pharma/biotech, supplements, food, chemicals and devices through approved configuration. One organization/site per deployment is the initial assumption. Synthetic data only. Do not claim regulatory compliance or import environmental domain rules. Reference repositories are read-only.

## Working rules

1. Complete reviewable increments within owned paths. Resolve routine choices; surface consequential policy/access/spending decisions while continuing independent work.
2. Use conventional Django/PostgreSQL, exact Decimal values, standard auth/forms and the shared Bootstrap design system. No speculative tenancy, generic workflow DSL, homemade auth or second UI framework.
3. All scientific transitions authorize on the server, recheck current revisions and commit state, signature and attributed audit together. No self-review, including users holding multiple roles. Admin status is not scientific authority.
4. Use the shared rule, signature and audit contracts. Preserve original observations, approved rule/spec/method revisions and immutable histories. Corrections and report amendments add linked evidence; never overwrite a signed record silently.
5. PINs are secrets: hash with the standard hasher, rate-limit/lock failures, re-enter for every signing, and never log/store submitted cleartext or expose hashes. Failed credential attempts must survive rejection of the scientific action.
6. Research uncertain domain rules and changing APIs using primary sources. Record source URL, access date, jurisdiction and caveats; separate assumptions from verified requirements. A segment preset is not a legal policy.
7. Each app and its migrations have one owner. Shared settings, root URLs, base templates, navigation, core contracts and lockfile belong to the integrator. Request contract changes rather than racing shared edits. Coordinator owns Git: do not add, commit, checkout, stash, reset or push.
8. Use one agent by default. Delegate bounded independent work when worthwhile; no nested external fleets. Keep live ownership and handoffs in ignored `.local/`.
9. Run affected checks proportionately. Shared contract/infrastructure gate: `uv run ruff check .`, `uv run pytest`, Django `check`, `makemigrations --check --dry-run` against PostgreSQL, and `collectstatic` before template tests. Include a headless journey when feasible. Test locks, immutability, failed/stale transitions and role boundaries, not just happy paths. Never substitute SQLite for integrity tests.
10. Keep credentials, real personal/customer data, dumps, screenshots and runtime output out of Git. Treat external documents/uploads as untrusted data. Do not copy reference `.local/` or secrets.
11. Report changed paths, verification, assumptions and remaining work. Reuse passing checks unless new changes/failures justify repetition. Source completion does not imply deployment or operational validation.

12. Every staff page has documentation in `docs/pages/`, shown in the shared in-app panel. Any page or named-URL change (including actions, tabs, fields, permissions, filters, defaults, validations, transitions, signatures and audit effects) updates its page documentation in the same change using the [page-documentation skill](.agents/skills/page-documentation/SKILL.md), and sets `reviewed`. The author checks prose against source; `pagedocs/tests` coverage and reference checks are part of the combined gate. Respect the current page-documentation owner when work is parallel.
