---
date: 2026-11-16
type: changed
impact: medium
title: Product renamed to OpenBGA QM LIMS
area: Whole application
pr: 41
---
The product is now OpenBGA QM LIMS, with the repository `openbga/qm-lims`. The name appears in the application, certificate and record PDFs, passkey and authenticator-app names, documentation and the presentation. Issued PDFs keep their original bytes.

## Technical notes

- Renamed the product to **OpenBGA QM LIMS** and the repository to `openbga/qm-lims` (the former `openbga/fresh-coa-lims` address redirects): application name, titles, top bar, footer, certificate and record PDFs, passkey and authenticator-app names, README, documentation, presentation and project links. The presentation moves to <https://openbga.github.io/qm-lims/> (the old address no longer serves it). The Python package is `openbga-qm-lims`, backup file names in the runbook start with `qm-lims-`, and the CI image tag is `qm-lims:ci`. Unchanged on purpose: the database name and user `open_qual`, the Render resources `fresh-coa-lims`, `fresh-coa-lims-db` and `fresh-coa-lims-demo-reset` and the demo at `fresh-coa-lims.onrender.com`, the backup manifest and restore report format identifiers (`fresh-coa-lims.backup-manifest/1`, `fresh-coa-lims.restore-check/1`, so existing backups still verify) and the `freshcoa-pagedocs-*` browser storage keys. Issued PDFs keep their original bytes.
