---
date: 2026-11-10
type: added
impact: high
title: First public source release
area: Whole application
---
OpenBGA QM LIMS is published as source under AGPL-3.0-only. It covers approved methods and specifications, sampling, lot and sample records, results with replicates, investigations, independent review and QC disposition, certificates of analysis, laboratory resources, stability, signatures, the audit trail and named user accounts.

## Technical notes

Initial public source release (project version 0.1.0), licensed AGPL-3.0-only. Implemented areas:

- Approved methods and specifications, sampling plans and sampling assignments, with independently approved revisions and frozen applicability snapshots on lot assignments.
- Lot and sample records, numeric observations with replicates, and method QC batches.
- Out-of-specification investigations with controlled assessment, retest and resample authorization, and conclusion.
- Independent signed review and QC disposition that checks assigned requirements, review state, investigations, independence and active holds.
- Immutable PDF certificates of analysis with signed issuance, amendments, stored bytes, snapshots and checksums.
- Laboratory resource records and method-specific analyst qualification authorization.
- Stability protocols and scheduled pulls, reserves, retention obligations and holds.
- Shared rule revisions, PIN signatures (hashed, rate-limited, re-entered for every signing) and attributed audit history.
- Named user accounts with explicit roles, signed account administration, session limits and a read-only Django admin.
- In-app page documentation for every staff page, and a static presentation website published with GitHub Pages.
- Sign-in throttling, a same-origin Content-Security-Policy and credential masking in error reports.
- Container image, CI workflow, a Docker Compose profile for local evaluation and a Render Blueprint for manual deployment.

Limits at the first release:

- Greater-than results and batch QC checks other than directly entered numeric values with inclusive limits are not supported. A method states that an instrument or a lot is required, not which one.
- Stability testing compares each result with its acceptance criterion. Trend rules, a significant change from the initial value, shelf-life evaluation, a hold on the lot after a failing result and reports to authorities are left to the laboratory.
- Manufacturer batch release is a separate decision and is not performed by the software.
- Multi-factor authentication, identity proofing, PIN recovery policy, backup schedules and storage, restore acceptance, retention and intended-use validation remain the responsibility of each deployment.
- Segment presets are synthetic drafts, not complete policies.
- No regulatory compliance, validation or certification is claimed. Use synthetic data only.
