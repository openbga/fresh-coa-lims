---
title: Reject lot
urls: quality:lot_reject
views: quality.rejection_views.lot_reject
templates: quality/closure.html
models: quality.Lot, core.ElectronicSignature, core.AuditEvent, core.PINCredential
reviewed: 2026-11-17
summary: Sign the rejection of a quarantined lot that failed its requirements or cannot be used. Quality role only. The lot is not released and keeps every record as shown.
---

## Common tasks
### Reject the lot
1. Review [[The lot now]], [[What stands in the way of release]] and [[Tests]]. Your signature freezes what they show.
2. Choose the [[Grounds for the rejection]] and enter the [[Reason for the rejection]].
3. Optionally name the deviation or nonconformance record in [[Record in the quality system]].
4. Enter your [[Signing username]] and [[Signature PIN]], then select [[Sign and reject the lot]].
### Clear what stops the rejection
1. If [[The lot cannot be rejected yet]] shows, conclude each open investigation and submit each test holding a result outside its limits.
2. Then open this page again and sign.
### Leave without signing
1. Select [[Cancel]]. Nothing is signed and the lot stays in quarantine.
## Good to know
- A lot need not be fully tested, or have failed, to be rejected. State why in the reason.
- You cannot reject a lot holding your own receipt, supplier certificate, sampling or test data, or a supplier result you proposed. Another quality person signs.
- Nothing is deleted. Open tests stay unfinished in the record, and the lot takes no more records.
- If the lot changes after you opened the page, nothing is signed. Review the lot as it is now and sign again.
- What happens to the material is decided and recorded in the quality system, not here.

## Purpose

Quality signs the rejection of a lot in quarantine: the lot did not meet its requirements or cannot be used. The lot is not released, takes no more receipt, sampling, certificate or test records, and keeps every record as the page showed it.

## Who can use it

- Sign-in required. **Quality** role only; every other role, and an account holding only Admin, receives 403 when it opens or submits the page. Admin status is not scientific authority.
- Never a user who authored the lot's receipt details, supplier certificate, sampling or test data, or who proposed a supplier result in place of a test, even with the quality role. Such a user sees the page with "Not permitted" and no form (status 403): "You cannot reject a lot containing your own receipt, supplier certificate, sampling or test data, or a supplier result you proposed in place of a test. Another quality person must sign."
- Requires an enrolled signature PIN.
- The **Reject lot** button on the lot record shows to every quality user while the lot is in Quarantine, including users who are then refused.

## Layout

- Breadcrumbs (Material lots, the lot, Reject lot), the lot number, material, record revision and a Quarantine label, and an introduction: rejection ends the quarantine, the lot is not released, takes no more receipt, sampling, certificate or test records and keeps every record; segregation and what happens to the material are decided and recorded in the quality system.
- **The lot now**: Rule set; Requirements ("Assigned", "On an applicability hold" or "Not assigned"); Receipt (supplier, supplier lot, delivery document, date, quantity and containers with their description, and the manufacturer with its location and lot when stated; or "Made on site"; or "Receipt details not recorded"); Examination on receipt (when receipt details exist); Supplier certificates (each current record, with "Does not meet the specification" and the tests, or "Withdrawn" with any tests it stated not meeting the specification; "None" when there are none); Supplier results in place of tests (each record with its test and Accepted, Awaiting acceptance or Withdrawn, or "None"); Active holds (identifier, kind and reason, or "None").
- **What stands in the way of release**: what the release gates report now, or "Nothing: the release gates find nothing missing or failing. A lot that meets its requirements can still be rejected; state why in the reason."
- **Tests**: Test (its number, with the test code and, for a retest, resample, rerun or repeat, its kind below), Status (Open, Awaiting review, Reviewed, Invalidated, Superseded, Not completed; "results not submitted" with the readings, and those outside the limits, for an open test holding results, "raw data attached, no result" for an open test holding only raw-data files), Outcome (Conforms or Out of specification) and Sample. Empty: "No tests were assigned to this lot." Note: "Tests stay as they are. An open test takes no more work once the lot is rejected and is kept in the record unfinished."
- **Investigations** (only when the lot has any): status Open, "Out-of-specification result confirmed" or "Original result invalidated".
- **The lot cannot be rejected yet** (only when refused): the reasons, "Nothing was changed. The lot stays in quarantine." and a back link.
- **Sign rejection**: statement of the signature, signer and a link to enroll or change the PIN, the form, **Cancel** and **Sign and reject the lot**.

## Actions

| Action | Shown when | Who | Result |
|---|---|---|---|
| **Sign and reject the lot** | The lot can be rejected and you may sign | Quality, independent of the lot's data | Lot becomes Rejected; message "Lot rejected. Its records are kept as they were signed."; returns to the lot record |
| **Cancel** / **Back to** the lot | Always | Quality | Nothing is signed |
| Test and investigation links | In the tables | Viewers of those pages | Open the test or investigation |

## Fields

| Field | Model field | Type / units | Required | Meaning and use |
|---|---|---|---|---|
| Grounds for the rejection | frozen with the lot | Choice | Yes | Results do not meet the requirements; Condition or documents on receipt; The supplier or the supplier's certificate; Another reason, stated below |
| Reason for the rejection | `AuditEvent.reason` | Text, max 2000 | Yes | What does not meet the requirements, or why the lot cannot be used |
| Record in the quality system | frozen with the lot | Text, max 200 | No | The deviation or nonconformance record that covers the decision and what happens to the material, for example NCR-2026-014 |
| Signing username | — | Text | Yes | Must be your own username |
| Signature PIN | `PINCredential` (checked, never stored) | Masked digits | Yes | Re-entered for every signature |
| Expected revision (hidden) | `Lot.revision` | Integer | Yes | Revision when the page was read |
| Basis (hidden) | — | Digest | Yes | Fingerprint of everything the page showed |

## Rules and hidden logic

- **Only a lot in Quarantine**: for a Released, Rejected or Cancelled lot the page redirects to the lot record with the error "Lot LOT-TEST-001 was released; its decision cannot change.", "... was rejected; its decision cannot change." or "... was cancelled as received in error."
- **Refusals** (listed on the page, nothing signed):
  - An investigation that is not closed: "<investigation> is open. Conclude it before the lot is rejected: the investigation is completed whatever is decided about the lot."
  - An open test holding a recorded result outside its limits that was not submitted, each reading judged as batch rejection judges it (as recorded or rounded half-up to the reporting precision, and a complete set of replicates as submission would calculate it): "<test> <code> holds a result outside its limits that was not submitted (<values>). Submit it first or, if the test cannot be completed, record that on the test, which opens an investigation, so that the result is evaluated and investigated." Results within their limits that were never submitted (a test that cannot be finished) do not stop the rejection; they are frozen as recorded.
- **Work that cannot be finished**: quality records on the test that it cannot be completed (Record that a test cannot be completed). A test holding a reading outside its limits then opens an investigation, to be concluded before the lot is rejected; any other test is repeated or left to its investigation, and a repeat is open work that does not stop the rejection. A test recorded as not completed is shown with the status "Not completed · recorded: READINGS" (and "(READINGS outside the limits)") as its record froze them, stays as signed and never refuses the rejection.
- **Not required**: the lot need not be fully tested, have requirements, or have failed. Open tests, tests awaiting review, active holds and supplier results standing in place of tests do not stop the rejection; they are frozen as shown.
- **What is frozen**: with the signature (meaning `rejected`, bound to the resulting lot revision) the lot stores what the page showed: requirements assignment, receipt details, what stood in the way of release, tests, investigations, supplier certificates and results, active holds, the grounds and the reference (schema `oq.lot-rejection/1`). The lot record shows it.
- **Stale page**: signing rereads the lot under its lock. If the revision or anything shown has changed: "Record changed. Reload and review before signing." or "The lot's record changed after this page was opened. Nothing was signed. Review the lot as it is now and sign again." The page then shows the lot as it is now; enter the PIN again. A form submitted while the lot could not be rejected, or while you were refused as an author, when the lot can be signed by the time the page is read again, shows the second message and signs nothing.
- **Failed signing attempts**: wrong username, PIN or session messages follow the usual signing rules; failed credential attempts are recorded even though the rejection is refused, and repeated failures lock the PIN.
- **Effects**: state, signature and an audit event are committed together. The lot's record revision rises by 1.
- **After rejection**: the lot takes no more samples, receipt details, certificates, results or tests; it cannot be released or cancelled. An open or submitted test stays unfinished in the record. Rejecting a QC batch that holds such a test still works; the test is left as it is. Stability pages refuse a rejected lot only when starting a study; reserve samples, retention obligations and holds may still be recorded for it.
- Not enforced by this page: segregation, return, reprocessing or destruction of the material, and the content of the quality-system record named in the reference.

## Related pages

- Lot record (opens after signing and when refused)
- Sign lot disposition (releasing instead)
- Cancel lot received in error
- [Signature PIN](/signature-pin/)
- [Material lots](/lots/)
