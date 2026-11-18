---
title: Conclude impact assessment
urls: impact:conclude
views: impact.views.assessment_conclude
templates: ops/sign.html
models: impact.Assessment, impact.Item, stability.Hold, core.ElectronicSignature, core.AuditEvent
reviewed: 2026-11-17
summary: Sign the conclusion of an impact assessment on the records and decisions shown. Quality only, never someone who took part in the assessment or produced data of its tests.
---

## Common tasks

### Conclude the assessment

1. Check the counts and the affected records shown.
2. Enter your [[Signing username]], a [[Reason for signing]] and your [[Signature PIN]].
3. Select [[Sign and conclude]]. You return to the record.

### Find out why you cannot conclude

1. If [[Not permitted]] shows, read the reason and select [[Back to record]].

## Good to know

- Every record needs a decision, and the cause must find nothing that is not in the assessment. Otherwise the page says "N record(s) have no decision." or asks you to find affected records again.
- You cannot conclude an assessment you started, added or decided a record of, placed a hold through, or produced test data for.
- Concluding freezes the records and decisions. Holds placed through the assessment stay until released.
- Five wrong PINs in a row lock your PIN for 15 minutes. Failed attempts are recorded.

## Purpose

Signs the conclusion with meaning **impact_assessed**. The records and decisions are frozen as evidence.

## Who can use it

- Sign-in required. **quality** role only; others, and an account holding only Admin, receive 403.
- Refused with a reason and no PIN control (403): "You started this assessment, added or decided one of its records, placed one of its holds or produced data of one of its tests. Another quality person concludes it."; "This impact assessment is no longer open."; or the blockers below.

## Layout

- Breadcrumbs (Impact assessments, IA-n, Conclude), then a signing dialog (a plain card without JavaScript): the record and revision, the meaning, key facts, the signer, the link to enrol or change the PIN, the form, **Cancel** and **Sign and conclude**. Opening the page never signs.
- **Key facts**: Assessment, Cause, Period of concern, Records ("N affected · N not affected"), then one line for each affected record (up to 30, then "N more affected, listed on the record").
- **Denied**: the facts, a red "Not permitted" notice with the reason and **Back to record**; the page answers 403.

## Actions

| Action | Shown when | Who | Result |
|---|---|---|---|
| **Sign and conclude** | Not denied | Quality, not an author | Signs with meaning **impact_assessed**; message "IA-n concluded."; returns to the record |
| **Cancel** | Always | Quality | Returns; nothing is signed |

## Fields

| Field | Model field | Type / units | Required | Meaning and use |
|---|---|---|---|---|
| Assessment, Cause, Period of concern, Records | — | Display | — | What the signature binds |
| Signing username | — | Text | Yes | Must equal your own username |
| Reason for signing | `Assessment.decision_reason`, audit reason | Text, max 2000 | Yes | Recorded with the signature and shown on the record |
| Signature PIN | `PINCredential` (checked, never stored) | Masked digits | Yes | Re-entered for every signature |
| Expected revision (hidden) | `Assessment.revision` | Integer | Yes | Revision shown when the page opened |

## Rules and hidden logic

- Meaning text: "You conclude the impact assessment on the records and decisions shown. They are frozen with your signature. Holds placed through it stay until released on their own pages; withdrawing or amending a certificate, retesting and the manufacturer's decisions on released material are separate."
- **Authors** who cannot conclude: whoever started it; whoever added a record by hand (a record found from the cause has no author); whoever decided a record; whoever placed a hold through it; and the data authors of its tests (observations including corrected originals, submission and QC batch records).
- **Blockers**, checked again under the lock when signing: "N record(s) have no decision." and "The cause finds N record(s) that are not in the assessment: find affected records again." A change to any record since the page opened raises the revision and the signing fails as stale: "Record changed. Reload and review before signing."
- **Identity, session and PIN**: you type your own username and re-enter the PIN for every signature. A wrong username or PIN, an expired session or a locked PIN is refused inline and nothing changes. Failed PIN attempts are counted and audited even though the action is rejected.
- **Effect**: one transaction sets the state to Concluded with the time and the reason, freezes the evidence `oq.impact-assessment/1` (every record with its label, current status, origin, basis, decision, reason, follow-up, who decided and when, its hold and the hold's state; the counts affected and not affected; the author identifiers), raises the revision, and writes the audit event `signed.impact_assessed` and an immutable signature bound to the new revision.
- **Database guards**: a concluded assessment must carry that evidence and a reason, and can no longer be changed or deleted, nor can its records.
- The assessment changes none of the records it names. Withdrawing or amending a certificate, retesting and decisions on material already released are done on their own pages.

## Related pages

- Impact assessment record (Cancel returns here)
- Withdraw impact assessment
- [Signature PIN](/signature-pin/)
