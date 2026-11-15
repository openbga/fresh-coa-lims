---
title: Review certificate
urls: reporting:issue_preview
views: reporting.views.issue_preview
templates: reporting/preview.html, reporting/_certificate.html
models: quality.Lot, reporting.Report, core.RuleSet, core.ElectronicSignature
reviewed: 2026-11-15
---

## Purpose

Shows the certificate that would be issued for a lot, built from the lot's current signed evidence, and says whether anything stops it. It is a preview: nothing is issued.

## Who can use it

- Sign-in required. Viewing requires **analyst**, **reviewer**, **quality**, **admin** or **auditor**.
- **Continue to signing** is shown only to **quality** users who are not blocked and did not author records on the lot.
- Other viewers, including administrators without the quality role, see a "Read only" note: only users with the quality role can issue or amend certificates.

## Layout

- **Header**: breadcrumbs, title "Review certificate · lot number", status "Preview, not issued" and the first 16 characters of the evidence hash.
- **Alerts** (only one shows, in this priority): "Cannot issue" with the list of reasons; "Not permitted" when you authored records on the lot; "Read only" for users without the quality role.
- **Certificates already opened for this lot**: links with recipient and status, when any exist.
- **Certificate preview**: Material and lot, Decision, Applied rules specification and methods, Results (per sample, or per reportable result for native lots, followed by a separate table of results accepted from the supplier's certificate when the lot has any; when this laboratory performed no test of a native lot, the sentence "No requirement of this lot was tested by this laboratory." takes the place of the laboratory's table), Holds and corrections (including linked investigations for native lots), optional Remarks, Electronic signatures, a **Technical identifiers** block (specification, method and assignment hashes, requirement sources) and the full evidence SHA-256. Hashes wrap so they stay complete and copyable on narrow screens.

## Actions

| Action | Shown when | Who | Result |
|---|---|---|---|
| **Continue to signing** | Quality role, no blockers, no authorship conflict | Quality | Opens the signing page, carrying the evidence hash you reviewed |
| Existing certificate links | Certificates exist for the lot | Any viewer | Open that certificate record |

## Fields

| Field | Model field | Type / units | Required | Meaning and use |
|---|---|---|---|---|
| Lot number, Material, Lot received | `Lot.number`, `Lot.material`, `Lot.created_at` | Text, UTC time | — | Identity of the lot |
| Decision | `ElectronicSignature` (lot, meaning approved) | Signer, time, lot revision | — | The signed QC disposition; states it is not manufacturer batch release |
| Rule set, Effective, Required tests | `RuleSet.code`, `version`, `revision`, `segment`, `effective_from`, `effective_until`, `policy` | Text, UTC time | — | Rule revision applied to the lot |
| Specification, Methods | — | Text | — | Shown only for lots released through native testing: the specification from the assignment frozen at disposition (code and version) and the currently required test methods (code and version, controlled document, suitability evidence, batch-QC need). Otherwise "No approved snapshot was supplied" (specification adds "; limits are those recorded with each result") |
| Results | `Result.test_code`, `value`, `unit`, `lower_limit`, `upper_limit` | Decimal with unit | — | Foundation lots: exact stored values, trailing zeros removed; limits shown as "low to high unit" |
| Reportable results (native testing) | `Lot.disposition_evidence` | Test, sample, method and revision, replicates as recorded (e.g. "<10", "Absent"), reportable result with unit (none for qualitative results), limits, review | — | Lots released through approved native testing show the evidence frozen at disposition, with the requirement source and assignment hash. A result reported by a contract laboratory adds a line under its method: "Tested by contract laboratory NAME, LOCATION. Report NUMBER dated DATE.", from the evidence frozen when the result was recorded. The Limits column shows the frozen acceptance text (for example "less than 1000 CFU/g" or "Absent in 25 g (expected: Absent)"); evidence frozen before acceptance text was published shows "low to high unit" with "no lower limit" / "no upper limit" when open. When every requirement was answered by an accepted supplier result, no empty table is printed: "No requirement of this lot was tested by this laboratory." The requirement sources under Technical identifiers then come from the supplier results |
| Results accepted from the supplier's certificate of analysis | `Lot.disposition_evidence` (supplier results) | Test, Supplier's result, Method and limits stated, Specification, Supplier's certificate, Accepted | — | Native lots, only when a supplier result was accepted in place of a test. A separate table under the laboratory's results, headed "Results accepted from the supplier's certificate of analysis. This laboratory did not perform these tests. Each result is stated on the supplier's certificate and was accepted in place of a test under a signed qualification of the supplier." Each row gives the test, the stated result with its unit (a qualitative result adds "Stated as:" with the certificate's words), the stated method with "Limits stated:", the specification's acceptance text, "NUMBER dated DATE, issued by ISSUER" with "Supplier NAME, LOCATION. Qualification SQ-n: EVIDENCE REFERENCE.", and the reviewer who signed the acceptance with the time ("Not accepted" if the signature is missing). All of it is the evidence frozen at disposition |
| Status, Analyst, Independent review | `Result.conforms`, `Result.analyst`, review signature | Text | — | Conforms / Out of limits; who recorded; who reviewed and when |
| Electronic signatures | `ElectronicSignature`; `Lot.disposition_evidence` | Meaning, Signer, Date and time, Bound to | — | One row per reviewed result, per accepted supplier result ("Supplier result assay accepted in place of a test", bound to "Acceptance SRA-n revision N"), the QC disposition and, once issued, the certificate |
| Holds and corrections | — | Text | — | Each hold with description and status, or "No holds in the hold snapshot."; corrections when any. If no hold snapshot were supplied: "A hold snapshot was not available to this system; hold status is not asserted by this certificate." |
| Evidence hash | — | SHA-256 | — | Fingerprint of everything shown; signing is refused if it changes |

## Rules and hidden logic

- **Blockers** (all re-checked at signing): lot has no signed QC disposition; disposition signature missing or not bound to the lot's current revision; no sample results; a sample missing a required test; a result without an independent signed review, reviewed by its own analyst, or with a review bound to another revision; a result outside its limits; QC disposition signed by an analyst of these results; any hold whose status is not closed, resolved, cleared or released ("Open hold: <description>.").
- **Native lots**: when the lot was released through approved native testing, the certificate uses the analytical evidence and the exact requirement assignment (identifier and hash) that the QC disposition was signed against, never today's requirements. Specification and methods come only from that assignment, which is looked up for this lot and checked against its hash. If it is missing, belongs to another lot or does not match, the page lists "The requirement assignment signed with the QC disposition could not be resolved and verified." and signing is not offered. It is also blocked if the analytical evidence was incomplete, holds neither a laboratory result nor an accepted supplier result ("No reportable native results are recorded for this lot."), a result lacks a signed review or replicates, an accepted supplier result lacks its signature ("The supplier result accepted for assay has no signed acceptance."), or the disposition was signed by an author of the results.
- **Supplier results on the certificate**: a supplier result is printed only when it was accepted in place of a test and stood when the QC disposition was signed. It is never mixed into the laboratory's results table. Other results of a supplier certificate are not printed. Not enforced by this page: a supplier qualification revoked after the acceptance is not shown here and does not block the certificate.
- **Frozen once issued**: an issued version's snapshot, PDF and hashes never change. Later holds or requirement changes affect only new previews, not issued certificates.
- **Authorship**: you cannot issue a certificate if you recorded the lot, a sample or a result, or (native lots) authored the frozen analytical records, even with the quality role. For an accepted supplier result the authors are the analyst who proposed it and everyone who recorded or corrected its supplier certificate. This page only hides **Continue to signing**; the server refuses at signing.
- **No mutation**: viewing writes no audit event. The page works for any lot, so an unreleased lot simply lists its blockers. Unknown lot: 404. GET only.

## Related pages

- [New certificate of analysis](/reports/new/)
- Sign and issue certificate (follows from this page), the certificate record, [Material lots](/).
