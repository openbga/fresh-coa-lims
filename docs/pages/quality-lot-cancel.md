---
title: Cancel lot received in error
urls: quality:lot_cancel
views: quality.rejection_views.lot_cancel
templates: quality/closure.html
models: quality.Lot, core.ElectronicSignature, core.AuditEvent, core.PINCredential
reviewed: 2026-11-17
---

## Purpose

Quality signs the cancellation of a lot that was recorded in error, such as a delivery recorded twice, before anything was done with its material. The lot and its records are kept, marked Cancelled, and its number is not used again.

## Who can use it

- Sign-in required. **Quality** role only; every other role, and an account holding only Admin, receives 403 when it opens or submits the page.
- Never a user who received the lot (created it) or authored any of its records: its receipt details, supplier certificate, sampling or test data, or a supplier result proposed in place of a test. Such a user sees "Not permitted" and no form (status 403): "You cannot cancel a lot you received or whose records you made. Another quality person must sign."
- Requires an enrolled signature PIN.
- The **Cancel lot received in error** button on the lot record shows to every quality user while the lot is in Quarantine, including users who are then refused.

## Layout

- Breadcrumbs (Material lots, the lot, Cancel lot received in error), the lot number, material, record revision and a Quarantine label, and an introduction.
- **The lot now**: Rule set; Requirements; Receipt; Examination on receipt; Supplier certificates; Supplier results in place of tests; Active holds, as on the rejection page.
- **The lot cannot be cancelled** (only when refused): the reasons, "Nothing was changed. The lot stays in quarantine." and a back link.
- **Sign cancellation**: statement of the signature, signer and a link to enroll or change the PIN, the form, **Cancel** and **Sign and cancel the lot**.

## Actions

| Action | Shown when | Who | Result |
|---|---|---|---|
| **Sign and cancel the lot** | The lot can be cancelled and you may sign | Quality, not the lot's receiver or author | Lot becomes Cancelled; message "Lot cancelled as received in error. Its records are kept."; returns to the lot record |
| **Cancel** / **Back to** the lot | Always | Quality | Nothing is signed |

## Fields

| Field | Model field | Type / units | Required | Meaning and use |
|---|---|---|---|---|
| What was recorded in error | `AuditEvent.reason` | Text, max 2000 | Yes | For example: the delivery was recorded twice, and the lot that holds it |
| Record in the quality system | frozen with the lot | Text, max 200 | No | The deviation or nonconformance record that covers the decision |
| Signing username | — | Text | Yes | Must be your own username |
| Signature PIN | `PINCredential` (checked, never stored) | Masked digits | Yes | Re-entered for every signature |
| Expected revision (hidden) | `Lot.revision` | Integer | Yes | Revision when the page was read |
| Basis (hidden) | — | Digest | Yes | Fingerprint of everything the page showed |

## Rules and hidden logic

- **Only a lot in Quarantine**: for a Released, Rejected or Cancelled lot the page redirects to the lot record with an error such as "Lot LOT-TEST-001 was released; its decision cannot change."
- **Refused once the material was used** (listed on the page, nothing signed):
  - "Samples were taken from this lot: <references>."
  - "Tests were assigned to this lot." (only when it has no samples)
  - "Reserve samples were recorded for this lot: <identifiers>."
  - "A stability study was started on this lot: <identifiers>."
  - After any of these: "Its material was received and handled, so its receipt was not made in error. If the lot cannot be used, reject it."
  - A supplier result proposed or accepted in place of a test that is not withdrawn: "<record> proposes or accepts the supplier's result for <test> in place of a test. Withdraw it first."
- **Not stopping it**: supplier certificates, receipt details and active holds do not stop the cancellation; they are frozen as shown.
- **What is frozen**: the signature (meaning `cancelled`, bound to the resulting lot revision) stores requirements, receipt details, supplier certificates and results, active holds and the reference (schema `oq.lot-cancellation/1`).
- **Stale page**: as for rejection: "Record changed. Reload and review before signing." or "The lot's record changed after this page was opened. Nothing was signed. Review the lot as it is now and sign again."
- **Failed signing attempts** are recorded even though the cancellation is refused; repeated PIN failures lock the PIN.
- **After cancellation**: the lot takes no more records, cannot be released or rejected, and is refused for new reserve samples, retention obligations and holds ("Lot LOT-TEST-001 was cancelled as received in error; it has no material.") and not offered when starting a stability study or placing those records.
- Not enforced by this page: whether the delivery really was a duplicate or mistake; that is the signer's judgment and the quality-system record.

## Related pages

- Lot record (opens after signing and when refused)
- Reject lot (when the material was handled but cannot be used)
- [Signature PIN](/signature-pin/)
- [Material lots](/lots/)
