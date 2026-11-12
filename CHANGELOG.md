# Changelog

All notable changes to OpenBGA Fresh CoA LIMS are recorded here. The format follows [Keep a Changelog](https://keepachangelog.com/en/1.1.0/). The project is pre-1.0 and does not yet promise a stable interface.

## [Unreleased]

### Changed

- Adopted the OpenBGA Fresh CoA LIMS name and certificate-and-leaf mark across the application, presentation and newly issued certificates.
- Moved the source repository and presentation to the `fresh-coa-lims` slug, with the hosted demo at `fresh-coa-lims.onrender.com`.

### Added

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

### Limits

- Numeric results with inclusive limits only; qualitative and exclusive requirements are held.
- Stability testing of released lots uses external evidence, because released lot records are immutable.
- Manufacturer batch release is a separate decision and is not performed by the software.
- Multi-factor authentication, identity proofing, PIN recovery policy, backup and restore acceptance, retention and intended-use validation remain the responsibility of each deployment.
- Segment presets are synthetic drafts, not complete policies.
- No regulatory compliance, validation or certification is claimed. Use synthetic data only.
