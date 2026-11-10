---
title: Review certificate
urls: reporting:issue_preview
views: reporting.views.issue_preview
templates: reporting/preview.html, reporting/_certificate.html
models: quality.Lot, reporting.Report, core.RuleSet, core.ElectronicSignature
reviewed: 2026-11-10
---

## Purpose

Shows the certificate that would be issued for a lot, built from the lot's current signed evidence, and says whether anything stops it. It is a preview: nothing is issued.

## Who can use it

- Sign-in required. Viewing requires **analyst**, **reviewer**, **quality**, **admin** or **auditor**.
- **Continue to signing** is shown only to **quality** users who are not blocked and did not author records on the lot.
- Other viewers see a "Read only" note: only users with the quality role can issue or amend certificates.

## Layout

- **Header**: breadcrumbs, title "Review certificate · lot number", status "Preview, not issued" and the first 16 characters of the evidence hash.
- **Alerts** (only one shows, in this priority): "Cannot issue" with the list of reasons; "Not permitted" when you authored records on the lot; "Read only" for users without the quality role.
- **Certificates already opened for this lot**: links with recipient and status, when any exist.
- **Certificate preview**: Material and lot, Decision, Applied rules specification and methods, Results (per sample, or per reportable result for native lots), Holds and corrections (including linked investigations for native lots), optional Remarks, Electronic signatures, a **Technical identifiers** block (specification, method and assignment hashes, requirement sources) and the full evidence SHA-256. Hashes wrap so they stay complete and copyable on narrow screens.

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
| Reportable results (native testing) | `Lot.disposition_evidence` | Test, sample, method and revision, replicates, reportable result with unit, limits ("no lower limit" / "no upper limit" when open), review | — | Lots released through approved native testing show the evidence frozen at disposition, with the requirement source and assignment hash |
| Status, Analyst, Independent review | `Result.conforms`, `Result.analyst`, review signature | Text | — | Conforms / Out of limits; who recorded; who reviewed and when |
| Holds and corrections | — | Text | — | Each hold with description and status, or "No holds in the hold snapshot."; corrections when any. If no hold snapshot were supplied: "A hold snapshot was not available to this system; hold status is not asserted by this certificate." |
| Evidence hash | — | SHA-256 | — | Fingerprint of everything shown; signing is refused if it changes |

## Rules and hidden logic

- **Blockers** (all re-checked at signing): lot has no signed QC disposition; disposition signature missing or not bound to the lot's current revision; no sample results; a sample missing a required test; a result without an independent signed review, reviewed by its own analyst, or with a review bound to another revision; a result outside its limits; QC disposition signed by an analyst of these results; any hold whose status is not closed, resolved, cleared or released ("Open hold: <description>.").
- **Native lots**: when the lot was released through approved native testing, the certificate uses the analytical evidence stored with the QC disposition, not a fresh calculation. It is blocked if that evidence was incomplete, has no results, a result lacks a signed review or replicates, or the disposition was signed by an author of the results.
- **Authorship**: you cannot issue a certificate if you recorded the lot, a sample or a result, or (native lots) authored the frozen analytical records, even with the quality role. This page only hides **Continue to signing**; the server refuses at signing.
- **No mutation**: viewing writes no audit event. The page works for any lot, so an unreleased lot simply lists its blockers. Unknown lot: 404. GET only.

## Related pages

- [New certificate of analysis](/reports/new/)
- Sign and issue certificate (follows from this page), the certificate record, [Material lots](/).
