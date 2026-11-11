# Provenance: derivation from OpenBGA Roots

Recorded 2026-11-10; reduced on 2026-11-11 to what provenance requires. The earlier reuse analysis remains in Git history.

| Item | Record |
| --- | --- |
| Source project | OpenBGA Roots, <https://github.com/openbga/roots>, a sibling BGASoft Inc. open-source project |
| Source baseline | Commit `d04a916` |
| Method | New repository seeded from a copy of selected files; source history not carried; fresh migrations per app |
| Retained | Django/PostgreSQL/Bootstrap/HTMX stack and tooling; design system (shared templates, `static/css/app.css` with its `--vr-*` tokens and `vr-` class prefix, icon sprite); audit, immutable-history, accounts/roles, form-dialog and grid patterns; versioned immutable PDF report pattern; Docker, CI and Render structure |
| Not retained | Environmental-laboratory rules, presets, seed data and exports; migration history; runtime `.local/` material, credentials and deployment data |
| Licence | Both projects are licensed AGPL-3.0-only by BGASoft Inc. (since 2026-11-11) |

Keep `LICENSE`, `NOTICE` and [third-party notices](../../THIRD_PARTY_NOTICES.md) when distributing. No environmental-laboratory rule applies to this product merely because code was reused.
