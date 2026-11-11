# Open Qual IQ product

Baseline: 2026-11-10. Open Qual IQ supports manufacturing quality-control laboratories in pharma/biotech, dietary supplements, food, chemical/industrial and medical devices in **one system**. Segment and destination-market obligations are controlled configuration, not separate products. One organization/site per deployment and online staff access are initial assumptions; neither a customer portal nor shared tenancy is part of this foundation.

The [regulatory matrix](research/regulations.md) is the authority for researched applicability, sources, jurisdiction and caveats. It supersedes the less complete regulatory inferences in [functional research](research/functionality.md). Both were researched on 2026-11-10. [Reuse research](research/reuse.md) explains the Open Roots IQ derivation. No environmental laboratory rule is inherited merely because code is reusable.

The platform and bounded native QC modules passed the integrated development gate on 2026-11-10. This is not a completed MVP or authorization for regulated production. The product supports a laboratory's quality system; it does not certify compliance with Part 11, cGMP, QMSR or ISO. Identity proofing, intended-use validation, qualified personnel, approved procedures and recovery remain deployment responsibilities. Laboratory approval, QC disposition and manufacturer release/QP certification are distinct decisions.

## Users and authority

| Role | Responsibility | Boundary |
|---|---|---|
| Analyst | Receive lots/samples, record observations and batch QC | Cannot review their own work |
| Reviewer | Review original records and results with PIN signature | Must be independent of authorship; return/correction flows retain history |
| Quality | Approve configuration and make QC disposition decisions | Cannot bypass missing/failing requirements or self-review |
| Admin | Read every laboratory area; manage named users and roles | No scientific mutation or signing without its designated lab role; no self-granted additional roles or removal of the last active admin |
| Auditor | Read records and inspect audit history | No scientific mutation |

The initial roles map to explicit Django groups. Later receiving, supervisor and metrology responsibilities may be split without weakening independence. Qualifications belong to the relevant method/activity, not merely to group membership. Account ownership must remain individual; shared signers are prohibited. Superusers receive no implicit laboratory or web account-management role. Accounts without a recognized role reach an access-guidance page instead of a permission loop.

Account administrators can create users, update identity, assign/revoke roles, deactivate/reactivate, clear PIN lockout, require PIN re-enrollment and force password replacement. Every administrative web change requires a reason and a fresh username/PIN signature bound to the resulting account revision. Initial and optional recovery passwords are entered privately and must be replaced before workspace access; no email delivery is assumed. Changes invalidate existing target sessions. Self-service password replacement requires the current password and a reason, with an audit event but no PIN, so credential recovery remains possible. The audited operator commands support bootstrap and controlled recovery; they are a separate trusted channel.

## Journeys

1. Receive an identified material/manufacturing lot in quarantine, attach the approved effective rule revision, assign approved specifications and a sampling plan, and record sampling provenance.
2. Assign tests from the frozen requirements; record observations, replicates and required batch QC with units, limits, raw-data references and attribution. Preserve applied rule/specification/method revisions.
3. Have a different qualified person inspect source data and audit history, then re-enter username and signing PIN to review the exact revision.
4. Have an authorized quality person evaluate completeness, failures and outstanding holds and sign the QC disposition. A laboratory decision never silently implies manufacturer batch release.
5. Issue a versioned CoA from approved evidence; amendment preserves the original and states the reason. Native issuance stores the evidence snapshot and PDF; later downloads return the issued bytes.

A failure creates a visible hold/investigation path. Retesting, resampling or invalidation must never erase the original result or allow testing into compliance. Stability protocols generate pull records with acceptance and evidence links. Released lot evidence is immutable, so new stability testing on a released lot currently requires controlled external evidence. Native observation recording and correction require a current approved analyst qualification for the test method and preserve the authorization evidence. Equipment/reagent use remains a separate explicit authorization workflow; those resources are not selected or checked by the observation form.

## Requirements and traceability

These identifiers are stable product requirements. “MVP” is the intended release scope, not a claim that implemented modules satisfy every applicable obligation. Delivery notes describe bounded functionality verified by the integrated development gate; intended-use and operational acceptance remain deployment responsibilities. Research IDs link to rows in the regulatory matrix; functional area numbers refer to the functional research table.

| Product ID | Required outcome | Research trace | Delivery |
|---|---|---|---|
| OQ-001 | Versioned, independently approved, effective-dated rule sets; explicit applicability and preserved decision basis | REG-CFG01–02; area 22 | Versioned rule contract and lot assignment snapshots implemented; broader multi-obligation resolution remains |
| OQ-002 | Immutable attributed audit events with before/after values, reasons, review and export | REG-CFG04, REG-E05, REG-DI03; area 9 | Shared audit/review/export and module events implemented; coverage requires integrated acceptance checks |
| OQ-003 | PIN re-entry per signature; signer, meaning, server timestamp and exact revision binding; atomic transition | REG-CFG05, REG-E07–11; area 6 | Atomic signatures and HTTP username/PIN re-entry implemented; operational validation remains |
| OQ-004 | Explicit permissions and independent review; qualified activity authorization; admin read-all/user management and safe no-role access | REG-P01–02, REG-P23, REG-E04; areas 6,17; admin policy user decision 2026-11-10 | Explicit roles, signed account lifecycle and method-specific observation qualification implemented; equipment/reagent execution integration remains |
| OQ-005 | Approved material/specification/method revisions, limits, sampling plans and suitability evidence | REG-P04–05, REG-P08, REG-S01, REG-S04, REG-ISO02; areas 1–3 | Versioned catalog, method QC and sampling plans implemented; specialized applicability remains |
| OQ-006 | Lot, shipment, supplier, sample and manufacturing traceability; contemporaneous source records | REG-P03, REG-P17–19, REG-P21, REG-S02–03, REG-DEV03; area 4 | Lot/sample identities and sampling provenance implemented; fuller supplier/shipment/manufacturing genealogy remains |
| OQ-007 | Exact observations, units, original data, calculations, test completeness and review | REG-P22–24, REG-DI01–02, REG-S05; areas 5–6 | Native numeric observations/replicates/batch QC and immutable corrections implemented; other result types held |
| OQ-008 | OOS holds, documented investigation, controlled retest/resample lineage and independent conclusion | REG-P20, REG-OOS01–03; area 10 | Phased OOS, authorized retest/resample and signed conclusion implemented; advanced OOT later |
| OQ-009 | Authorized QC disposition blocked by missing/failing tests, unresolved investigations and holds | REG-P07, REG-S06, REG-F01, REG-DEV02; area 7 | Assigned-specification, analytical and active-hold gates integrated; broader applicability remains |
| OQ-010 | Versioned immutable CoA/evidence export, signature manifestation and amendments | REG-E03, REG-E07–08, REG-ISO03, REG-ICH03; area 8 | Native signed PDF issuance, frozen versions and amendments implemented |
| OQ-011 | Equipment fitness, calibration status, reagent/standard provenance and qualification evidence | REG-P06, REG-P16, REG-P24, REG-ISO01, REG-USP01–02; areas 12–13,17 | Equipment/reagent records and explicit use authorization implemented; observation qualification integrated, resource selection remains |
| OQ-012 | Stability/reserve records, lot/container/condition/protocol links and retention holds | REG-P09, REG-P11, REG-S07, REG-ICH06; area 14 | Native protocols/pulls/reserves and evidence links implemented; released-lot testing uses external evidence |
| OQ-013 | Retention calculated from applicable anchors; all obligations/holds clear before disposal | REG-CFG03, REG-P14, REG-S08, REG-F05 | Anchored obligations and hold/disposal blockers implemented; no disposal action |
| OQ-014 | Controlled QMS/ERP/document links with stable IDs, revisions and retrievable evidence | REG-P18, REG-P25–26, REG-DEV01, REG-ISO04; areas 11,19–21 | Controlled evidence references available; complete ERP/QMS integration and native CAPA remain |
| OQ-015 | Food verification/review and market/customer overlays reflect actual applicability | REG-F02–06, REG-EU01–07, REG-ISO01–04 | Configuration building blocks implemented; specialized workflows and local applicability review remain |
| OQ-017 | Page-specific documentation for every staff page, kept accurate with page changes | User requirement, 2026-11-10; usability and controlled operational knowledge | Shared documentation panel and coverage gate |
| OQ-016 | Validated operation, controlled changes, access, backup, restore and inspection copies | REG-P27, REG-E02–04, REG-EU04–06, REG-GAMP01 | Deployment gate, not a software certification |

## In-app page documentation

Every staff page offers documentation from an icon at the top-right of the top bar. It opens a resizable right-side panel (a full-width overlay on narrow screens), follows navigation, and remembers its open/closed state and width in the browser. Each entry explains purpose, permissions, layout and every tab, action and field, naming `model.field` where applicable. It also explains hidden filters, defaults, permission conditions, transitions, validations and signature/audit effects. Documentation is derived from source, labels unverified policy as an assumption, and changes with the page. Automated coverage and reference checks are part of the release gate; prose accuracy remains the author’s responsibility.

## Implemented scope, acceptance and later work

| Stage | Scope | Acceptance boundary |
|---|---|---|
| Implemented modules | Shared rules/signatures/audit; versioned catalog and sampling; numeric testing/replicates/QC/OOS; laboratory authorization; stability/retention/holds; native PDF CoA | Combined PostgreSQL and native end-to-end browser checks passed on 2026-11-10; intended-use and operational acceptance remain |
| Remaining MVP integration/policy | Full applicable supplier/receipt evidence, equipment/reagent gating through analytical execution, destination/customer applicability, supported assay coverage and operational validation | Complete accepted/failed/corrected/amended journeys and traceability to every applicable requirement |
| Later capability | Advanced SPC/OOT, automated instrument interfaces, broader inventory/ELN/CAPA, specialized assays and environmental monitoring | Separate scoped acceptance and applicability review |

The native analytical contract supports numeric results and inclusive bounds. A declared reporting precision rounds the replicate mean half-up before comparison; `reporting_decimals=null` means exact comparison without rounding. Submission rejects a nonterminating mean or an exact mean requiring more than eight decimal places rather than silently rounding it. Individual replicate limits are checked when configured. Qualitative results and exclusive bounds may be represented upstream but remain held by native testing. No preset may silently bypass that boundary.

Once native tests exist, the lot requirements cannot be reassigned; controlled test/requirement supersession is not implemented. New QC batches offer only currently effective approved method revisions. Tests frozen to an older revision cannot use a newer-method batch, and creating a new batch for their old revision is intentionally unavailable.

Production QC disposition requires a native assignment and passing analytical/hold checks. The original manual-limit result path is DEBUG-only and unavailable once a lot has native assignments; mixed evidence blocks disposition. Released lots cannot accept new scientific results. Stability studies on those lots therefore retain external controlled test evidence rather than reopening the released lot.

Five editable segment presets are examples requiring quality-owner review. They are not authoritative legal policies, complete panels or production defaults. Universal audit, signature linkage and no-self-review cannot be disabled by a preset. Unresolved applicability must hold decisions; a generic preset cannot authorize a specialized assay. Deferred native functionality requires a controlled external process before the corresponding regulated work is supported.

## Decisions and remaining policy

| Topic | Decision or open responsibility |
|---|---|
| Product breadth | All five segments; no segment-specific forks |
| Data and credentials | Synthetic demonstration data only; credentials supplied locally, never committed |
| Time | UTC initial deployment default; explicit zone display and immutable historical timestamps |
| Signing | Separate hashed PIN, 8–32 digits; username/PIN re-entry for HTTP signing, five-failure/15-minute lock, 15-minute idle and 8-hour absolute session defaults; identity/MFA/recovery validation remains |
| Hosting | Authorized Render web 1c-2g and PG17 0.5c-1g/5 GB in Virginia after integrated checks; automatic deployment off |
| Pending operational decisions | Exact assays/specifications, applicability ownership, training evidence, signer identity verification, recovery procedures, retention schedules, RPO/RTO and production validation |
