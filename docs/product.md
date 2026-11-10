# Open Qual IQ product

Baseline: 2026-11-10. Open Qual IQ supports manufacturing quality-control laboratories in pharma/biotech, dietary supplements, food, chemical/industrial and medical devices in **one system**. Segment and destination-market obligations are controlled configuration, not separate products. One organization/site per deployment and online staff access are initial assumptions; neither a customer portal nor shared tenancy is part of this foundation.

The [regulatory matrix](research/regulations.md) is the authority for researched applicability, sources, jurisdiction and caveats. It supersedes the less complete regulatory inferences in [functional research](research/functionality.md). Both were researched on 2026-11-10. [Reuse research](research/reuse.md) explains the Open Roots IQ derivation. No environmental laboratory rule is inherited merely because code is reusable.

This is a platform foundation, not a completed MVP or authorization for regulated production. The product supports a laboratory's quality system; it does not certify compliance with Part 11, cGMP, QMSR or ISO. Identity proofing, intended-use validation, qualified personnel, approved procedures and recovery remain deployment responsibilities. Laboratory approval, QC disposition and manufacturer release/QP certification are distinct decisions.

## Users and authority

| Role | Responsibility | Boundary |
|---|---|---|
| Analyst | Receive lots/samples and record observations in the foundation | Cannot review their own work |
| Reviewer | Review original records and results with PIN signature | Must be independent of authorship; return/correction flows retain history |
| Quality | Approve configuration and make QC disposition decisions | Cannot bypass missing/failing requirements or self-review |
| Admin | Account/configuration administration | Administrative status alone grants no scientific approval |
| Auditor | Read records and inspect audit history | No scientific mutation |

The initial roles map to explicit Django groups. Later receiving, supervisor and metrology responsibilities may be split without weakening independence. Qualifications belong to the relevant method/activity, not merely to group membership. Account ownership must remain individual; shared signers are prohibited.

## Journeys

1. Receive an identified material/manufacturing lot in quarantine, attach the approved effective rule revision, and record its sample.
2. Record the test observation with exact value, unit, limits and attribution; preserve the applied rule/specification revision.
3. Have a different qualified person inspect source data and audit history, then re-enter their signing PIN to review the exact revision.
4. Have an authorized quality person evaluate completeness, failures and outstanding holds and sign the QC disposition. A laboratory decision never silently implies manufacturer batch release.
5. Issue a versioned CoA from approved evidence; amendment preserves the original and states the reason. This is a subsequent package, not part of the first thin journey.

A failure creates a visible hold/investigation path. Retesting, resampling or invalidation must never erase the original result or allow testing into compliance. Stability pulls and in-process samples reuse the same testing/review spine. Equipment, reagent and training evidence gate work where applicable.

## Requirements and traceability

These identifiers are stable product requirements. “MVP” is the intended release scope, not a statement that the current foundation satisfies it. Research IDs link to rows in the regulatory matrix; functional area numbers refer to the functional research table.

| Product ID | Required outcome | Research trace | Delivery |
|---|---|---|---|
| OQ-001 | Versioned, independently approved, effective-dated rule sets; explicit applicability and preserved decision basis | REG-CFG01–02; area 22 | Foundation contract; multi-obligation resolution in MVP |
| OQ-002 | Immutable attributed audit events with before/after values, reasons, review and export | REG-CFG04, REG-E05, REG-DI03; area 9 | Foundation; full module coverage in MVP |
| OQ-003 | PIN re-entry per signature; signer, meaning, server timestamp and exact revision binding; atomic transition | REG-CFG05, REG-E07–11; area 6 | Foundation; operational validation before use |
| OQ-004 | Explicit permissions and independent review; qualified activity authorization | REG-P01–02, REG-P23, REG-E04; areas 6,17 | Foundation roles; qualification gates in MVP |
| OQ-005 | Approved material/specification/method revisions, limits, sampling plans and suitability evidence | REG-P04–05, REG-P08, REG-S01, REG-S04, REG-ISO02; areas 1–3 | MVP |
| OQ-006 | Lot, shipment, supplier, sample and manufacturing traceability; contemporaneous source records | REG-P03, REG-P17–19, REG-P21, REG-S02–03, REG-DEV03; area 4 | Thin foundation; full receipt in MVP |
| OQ-007 | Exact observations, units, original data, calculations, test completeness and review | REG-P22–24, REG-DI01–02, REG-S05; areas 5–6 | Thin foundation; worksheets/QC in MVP |
| OQ-008 | OOS holds, documented investigation, controlled retest/resample lineage and independent conclusion | REG-P20, REG-OOS01–03; area 10 | MVP; advanced OOT later |
| OQ-009 | Authorized QC disposition blocked by missing/failing tests, unresolved investigations and holds | REG-P07, REG-S06, REG-F01, REG-DEV02; area 7 | Thin foundation; full gates in MVP |
| OQ-010 | Versioned immutable CoA/evidence export, signature manifestation and amendments | REG-E03, REG-E07–08, REG-ISO03, REG-ICH03; area 8 | MVP |
| OQ-011 | Equipment fitness, calibration status, reagent/standard provenance and qualification evidence | REG-P06, REG-P16, REG-P24, REG-ISO01, REG-USP01–02; areas 12–13,17 | MVP gates and controlled evidence; broader operations later |
| OQ-012 | Stability/reserve records, lot/container/condition/protocol links and retention holds | REG-P09, REG-P11, REG-S07, REG-ICH06; area 14 | MVP evidence links; native scheduling later |
| OQ-013 | Retention calculated from applicable anchors; all obligations/holds clear before disposal | REG-CFG03, REG-P14, REG-S08, REG-F05 | MVP; no disposal in foundation |
| OQ-014 | Controlled QMS/ERP/document links with stable IDs, revisions and retrievable evidence | REG-P18, REG-P25–26, REG-DEV01, REG-ISO04; areas 11,19–21 | MVP links; native CAPA/ERP later |
| OQ-015 | Food verification/review and market/customer overlays reflect actual applicability | REG-F02–06, REG-EU01–07, REG-ISO01–04 | MVP configuration; specialized workflows later |
| OQ-016 | Validated operation, controlled changes, access, backup, restore and inspection copies | REG-P27, REG-E02–04, REG-EU04–06, REG-GAMP01 | Deployment gate, not a software certification |

## Foundation, MVP and later

| Stage | Scope | Exit evidence |
|---|---|---|
| This foundation | Shared rules, signatures, audit, roles, shell and one minimal lot/sample/result/review/disposition path | PostgreSQL contract tests and a synthetic browser journey |
| MVP completion | Full specifications/methods/sampling, worksheets/QC/OOS, receipt detail, CoA, evidence links, retention and applicable equipment/training gates | Complete accepted/rejected/corrected lot journeys; immutable export; traceability to every applicable requirement |
| Later native capability | Stability automation, environmental monitoring, advanced SPC/OOT, instrument interfaces, inventory, ELN and full CAPA | Separate scoped acceptance and applicability review |

Five editable segment presets are examples requiring quality-owner review. They are not authoritative legal policies, complete panels or production defaults. Universal audit, signature linkage and no-self-review cannot be disabled by a preset. Unresolved applicability must hold decisions; a generic preset cannot authorize a specialized assay. Deferred native functionality requires a controlled external process before the corresponding regulated work is supported.

## Decisions and remaining policy

| Topic | Decision or open responsibility |
|---|---|
| Product breadth | All five segments; no segment-specific forks |
| Data and credentials | Synthetic demonstration data only; credentials supplied locally, never committed |
| Time | UTC initial deployment default; explicit zone display and immutable historical timestamps |
| Signing | Separate hashed PIN, 8–32 digits; five failed attempts cause a 15-minute lock; laboratory must approve identity/session/recovery policy |
| Hosting | Authorized Render web 1c-2g and PG17 0.5c-1g/5 GB in Virginia after integrated checks; automatic deployment off |
| Pending operational decisions | Exact assays/specifications, applicability ownership, training evidence, signer identity verification, recovery procedures, retention schedules, RPO/RTO and production validation |
