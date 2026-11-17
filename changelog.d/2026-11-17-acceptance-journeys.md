---
date: 2026-11-17
type: added
impact: high
title: Acceptance journeys run passing, failing, corrected, rejected and amended records end to end
area: Deployment
pr: 49
---
A deployment can run five record journeys (passing, failing, corrected, rejected and amended) with the release it is about to use, in a new database of its own environment. Each step records what was expected and what happened, including the refusals, and the run keeps a report, each lot's record export and the certificates with their checksums as evidence for the laboratory's own acceptance. The journeys use synthetic configuration, not the laboratory's.

## Technical notes

Acceptance journeys: `python manage.py acceptance_journeys --database NAME --output DIR --operator NAME` runs five journeys (passing, failing, corrected, rejected and amended records) end to end through the application's services in a new database migrated to the release, refusing a database other than the one named, one that holds any account or one not migrated to exactly this release. Each step records what was expected and observed and the product requirements it gives evidence for, including refusals (self-review, a wrong PIN counted and audited, disposition or rejection by an author, release while an investigation is open, a second retest, invalidation by a failing retest, requirements, a disposition or a certificate for a rejected lot, a stale amendment, and direct database changes to a certificate, an observation, a signature and an audit event). The evidence folder holds `report.html`, `report.json` (`oq.acceptance-journeys/1`), each lot's record export, the certificates and `SHA256SUMS`; the command exits nonzero when a step failed. Guidance in `docs/operations.md` ("Acceptance journeys").
