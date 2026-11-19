---
title: Conclude reassessment
urls: quality:reassessment_conclude
views: quality.reassessment_views.reassessment_conclude
templates: ops/sign.html
models: quality.Reassessment, quality.Lot, analytical.AnalyticalTest, core.ElectronicSignature, core.AuditEvent
reviewed: 2026-11-19
summary: Sign the conclusion of a reassessment: the material is suitable until a new retest date, or its use ends. Quality only, never who started it, produced its test data or investigated its results.
---

## Common tasks

### Find the material suitable

1. Check the lot, the dates and each test result shown. Choose the outcome [[Suitable for use until a new retest date]].
2. Enter the [[New retest date]], your [[Signing username]], a [[Reason for signing]] and your [[Signature PIN]].
3. Select [[Sign and conclude]]. The lot's retest date in force becomes the new date.

### End the use of the lot

1. Choose [[Not suitable: its use ends]] and leave [[New retest date]] empty.
2. Enter your [[Signing username]], a [[Reason for signing]] and your [[Signature PIN]], then select [[Sign and conclude]].

### Find out why you cannot conclude

1. If [[Not permitted]] shows, read the reason and select [[Back to record]].

## Good to know

- Suitable needs every required test to have a reviewed result that conforms and nothing in progress. The outcome help says why it is not possible when it is not.
- The new retest date must be after today and not after the lot's expiry date. If a rule set reserves release, Suitable also needs your Release decisions qualification; [[Outcome]] says so.
- Not suitable ends the lot's use: it keeps its released disposition as signed, takes no certificate and is not reassessed again.
- A failure confirmed by an investigation is concluded here as not suitable. It cannot be withdrawn.
- Five wrong PINs in a row lock your PIN for 15 minutes. Failed attempts are recorded even though nothing is signed.

## Purpose

Sign a reassessment with meaning **reassessed**: the lot's material is suitable for use until a new retest date, or its use ends. The signature freezes the results the conclusion rests on.

## Who can use it

- Sign-in required. **quality** role only; others, and an account holding only Admin, receive 403.
- Never the person who started the reassessment, produced test data for any of its tests (observations including corrected originals, submission, QC batch records) or investigated any of its results, even with the quality role. The page then shows "You started this reassessment, produced test data for it or investigated one of its results. Another quality person concludes it." with no PIN control (403). Assigning tests, reviewing a test, authorizing a retest or concluding an investigation is not authorship.
- Where a rule set the lot is under reserves release (policy key `authorization`, `release`), concluding Suitable, which keeps the material in use, also needs an approved, current Release decisions qualification for each activity named. The rule sets are the versions in force now, not the ones frozen at release. Without it the Outcome help reads "You cannot conclude that the material is suitable: …" and the form starts on Not suitable. Not suitable is not reserved. When neither outcome can be signed the page is denied (403).
- Also refused with the reason and no PIN control (403): "This reassessment is no longer open."; and, while testing is in progress, "Testing is in progress: …" with each item (a test awaiting review, an open test holding results or raw data that were not submitted, or an open investigation).

## Layout

- Breadcrumbs (Material lots, the lot number, the reassessment, Conclude), then a signing dialog (a plain card without JavaScript): the record and its revision, the meaning, key facts, the signer, the link to enrol or change the signature PIN, the form, **Cancel** and **Sign and conclude**. Opening the page never signs.
- **Key facts**: Lot (number and material), Reassessment (RA-n and sample), Retest date in force, Expiry date, **If suitable** (when a reservation applies and you hold the qualification): "This signature relies on your qualification QUAL-3, for release decisions in “REL-TEST” (Rule set RS-TEST v2), and records it."; one line for each test code with its reported result and "Conforms", "Does not conform" or "Not decided", and "Not complete" with what is still open.
- **Denied**: the facts, a red "Not permitted" notice with the reason and **Back to record**; the page answers 403.

## Actions

| Action | Shown when | Who | Result |
|---|---|---|---|
| **Sign and conclude** | Not denied | Quality, not an author of the reassessment | Signs with meaning **reassessed**; returns to the reassessment record with "RA-n concluded." |
| **Cancel** / Escape | Always | Any | Returns to the record; nothing is signed |

## Fields

| Field | Model field | Type / units | Required | Meaning and use |
|---|---|---|---|---|
| Lot, Reassessment, Retest date in force, Expiry date, test lines | — | Display | — | What the signature binds. The results are read again when signing |
| Outcome | `Reassessment.outcome` | "Suitable for use until a new retest date" or "Not suitable: its use ends" | Yes | Starts on Not suitable when the material cannot be found suitable now, with the help "The material cannot be found suitable: …"; otherwise on Suitable |
| New retest date | `Reassessment.retest_on` | Date | For Suitable; must be empty for Not suitable | After today, not after the lot's expiry date |
| Signing username | — | Text | Yes | Must equal your own username |
| Reason for signing | `Reassessment.decision_reason`, audit event reason | Text, max 2000 | Yes | Recorded with the signature |
| Signature PIN | `PINCredential` (checked, never stored) | Masked digits | Yes | Re-entered for every signature |
| Expected revision (hidden) | `Reassessment.revision` | Integer | Yes | Revision shown when the page opened |

## Rules and hidden logic

- Meaning text: "You conclude the reassessment of the lot's material on the results shown. Suitable: the material may be used until the new retest date, which becomes the lot's retest date in force. Not suitable: the lot's use ends; it keeps its released disposition as signed, takes no certificate and is not reassessed again."
- **Release decisions**: a Suitable signature is refused before the PIN is checked when you lack the qualification ("Rule set RS-TEST v2 reserves release decisions for people qualified for “REL-TEST”. You hold no approved, current qualification for it."), and again under the locks. The qualifications relied on are frozen in the reassessment's result evidence and shown on its record as "Concluded under". Revoking one later changes nothing already signed.
- **Suitable is refused** unless: a test is assigned ("No test of the reassessment is assigned."); nothing blocks ("Testing is not complete: …": a test open or awaiting review, a test code with no reviewed result, an open investigation); and every required test code has a reviewed conforming result ("A result does not meet its acceptance criterion; the material is not suitable."). The required codes are those the specifications in force require at signing, not only those assigned: a test the specification added after the tests were assigned shows "<code>: no test is assigned." until it is assigned on the reassessment page and decided; when the requirements in force cannot be resolved, "The requirements in force cannot be resolved: …" refuses Suitable. A result under investigation counts only when the investigation invalidated the original; one that confirmed the failure counts as failing.
- **Retest date**: "Enter the new retest date." when missing or not a date; "The new retest date must be after today." (the local date of signing); "The new retest date cannot be after the lot's expiry date, <date>." The expiry date is the one in force.
- **Not suitable** is refused only while testing is in progress ("Testing is in progress: …") and with a date: "A reassessment that ends the material's use sets no date." It can be signed without tests or with conforming results; the reason says why.
- **Everything is checked again when signing**, under the reassessment's lock: it is still open, you are not an author, and the results are those of the revision you saw. A change to its tests since the page opened raises the revision and the signing fails as stale.
- **Identity, session and PIN**: you must type your own username and re-enter your signature PIN for every signature; a wrong username, wrong PIN, expired session or locked PIN is refused with an inline message and nothing changes. Failed PIN attempts are counted and audited even though the action is rejected (five failures lock the PIN for 15 minutes).
- **Stale page**: "Record changed. Reload and review before signing."
- **Effect**: one transaction sets the state to Concluded with the outcome, the new retest date (Suitable), the time and the reason, freezes the results (each test's result, acceptance criterion, method, review signature, investigations, blockers and the authors) with the dates it started from, raises the revision by 1, writes the audit event `signed.reassessed` and an immutable signature bound to the new revision.
- **Locks**: the signature locks the lot before the reassessment, so a certificate being issued or amended meanwhile waits and then reads the outcome; none is issued beside a conclusion that ends the lot's use.
- **What it changes for the lot**: the lot's own record, revision, dates as frozen at release and disposition are not changed. After a Suitable conclusion the lot's retest date in force is the new date: the lot record and list show it, a lot whose retest date had been reached is no longer shown as Retest due, a certificate prints it with a "Reassessed" line, and a further reassessment can start. After Not suitable the lot shows "Use ended"; no certificate is issued or amended and it is not reassessed again.
- **Certificates**: whoever started, tested or investigated the reassessment that set the retest date in force is counted among the authors of a certificate that prints it, so cannot issue or amend it.
- Not enforced by this page: how the laboratory chooses the new date, or what becomes of material whose use ended.

## Related pages

- Reassessment record (Cancel returns here)
- Withdraw reassessment (the alternative for a reassessment started in error)
- Lot record
- [Signature PIN](/signature-pin/)
