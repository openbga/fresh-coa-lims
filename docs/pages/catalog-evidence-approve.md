---
title: Approve method evidence record
urls: catalog:evidence_approve
views: catalog.evidence_views.evidence_approve
templates: ops/sign.html
models: catalog.MethodEvidence, catalog.MethodEvidenceCharacteristic, core.ElectronicSignature, core.AuditEvent, core.PINCredential
reviewed: 2026-11-19
summary: Sign the approval of a draft evidence record. Quality only, and never the person who recorded or changed it. The signature freezes the record and its characteristics.
---

## Common tasks

### Approve the record

1. Check the details and the number of characteristics shown.
2. Enter your [[Signing username]], a [[Reason for signing]] and your [[Signature PIN]].
3. Select [[Sign and approve]]. You return to the record.

### Find out why you cannot approve

1. If [[Not permitted]] shows, read the reason and select [[Back to record]].

## Good to know

- You cannot approve a record you recorded or changed, including by adding or removing characteristics.
- Before any PIN is asked, the page says what is missing: characteristics, or Deviations when a criterion was not met but the conclusion is "Suitable".
- Approval freezes the record. A method version can then rely on it if it concludes the method is suitable.
- Five wrong PINs in a row lock your PIN for 15 minutes. Failed attempts are recorded.

## Purpose

Signs the approval of a draft evidence record, with meaning **approved**.

## Who can use it

- Sign-in required. **quality** role only; others, including admin alone, receive 403. The role is checked before the record is looked up.
- Refused with a reason, no PIN control and status 403: "Only a draft record can be approved.", "You recorded or changed this record; another quality person approves it." or "Not ready for approval." followed by what is missing (the same problems as "Before approval" on the record).

## Layout

- Breadcrumbs (Method evidence, MEV-n, Approve), then a signing dialog (a plain card without JavaScript): the record and revision, what the signature means, the facts, the signer, the link "Enroll or change your signature PIN", the form, **Cancel** and **Sign and approve**. Opening the page never signs.
- **Facts**: the record details as on the record page, "Characteristics" ("N evaluated") and Recorded by.
- **Denied**: a red "Not permitted" notice with the reason and **Back to record**.

## Actions

| Action | Shown when | Who | Result |
|---|---|---|---|
| **Sign and approve** | Not denied | Quality, independent | Signs; message "MEV-n approved."; returns to the record |
| **Cancel** | Not denied | Quality | Returns; nothing is signed |

## Fields

| Field | Model field | Type / units | Required | Meaning and use |
|---|---|---|---|---|
| Signing username | — | Text | Yes | Must equal your own username |
| Reason for signing | audit reason | Text, max 2000 | Yes | Recorded with the signature |
| Signature PIN | `PINCredential` (checked, never stored) | Masked digits | Yes | Re-entered for every signature |
| Expected revision (hidden) | `MethodEvidence.revision` | Integer | Yes | Revision shown when the page opened |

## Rules and hidden logic

- Meaning text: "You approve this record and its characteristics as the evidence of the method's suitability for the intended use stated. Your signature freezes them."
- **Checks at signing** (again under the lock): a draft; you did not record or change it; and the same problems as "Before approval" on the record ("Add the characteristics that were evaluated, each with its criterion and result."; the not-met criterion needing Deviations; "The report is dated in the future."). A transfer waiver needs no characteristics. The page refuses before any PIN is asked while one of these problems remains.
- **Stale record**: "Record changed. Reload and review before signing." when the revision changed.
- **Effect**: one transaction stores the frozen content (the record and its characteristics) and its hash, sets the state to Approved with the time, raises the revision, and writes audit event `signed.approved` and an immutable signature bound to the new revision.
- **PIN and session**: the usual refusals (no PIN, wrong PIN, lock, different username, expired session); failed attempts are audited though the approval is refused.
- **Database guards**: an approved record and its characteristics can no longer be changed or deleted.

## Related pages

- Method evidence record
- [Signature PIN](/signature-pin/)
