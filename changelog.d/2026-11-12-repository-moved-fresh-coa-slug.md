---
date: 2026-11-12
type: changed
impact: low
title: Repository and demonstration move to the fresh-coa-lims address
area: Deployment
pr: 9
---
The source repository, the presentation and the hosted demonstration use the `fresh-coa-lims` name in their addresses. The product name is unchanged.

## Technical notes

- Moved the source repository and presentation to the `fresh-coa-lims` slug, with the hosted demo at `fresh-coa-lims.onrender.com`.

The database name and user `open_qual` and the browser preference storage keys are kept, so stored records and saved panel settings are unaffected. Automatic Render deployment stayed off in this change.
