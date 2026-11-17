---
title: Supplier qualification record
urls: suppliers:qualification_detail
views: suppliers.qualification_views.qualification_detail
templates: ops/record.html
models: suppliers.SupplierQualification, suppliers.Supplier, catalog.Material, quality.SupplierResultAcceptance, quality.Lot, core.ElectronicSignature, core.AuditEvent
reviewed: 2026-11-17
summary: One supplier qualification: the evidence, the tests and dates it covers, its signatures, and every supplier result proposed or accepted under it. Quality users approve or revoke it here.
---

## Common tasks
### Approve the qualification
1. Select [[Approve]]. It shows to quality users while it awaits approval, never to the person who recorded it.
2. Sign with your PIN on that page.
### Revoke the qualification
1. Select [[Revoke]]. It shows to quality users while the qualification is approved, including when expired.
2. Sign with your PIN on that page.
### See which supplier results relied on it
1. Under [[Supplier results that relied on this qualification]], select an acceptance or a lot to open it.
## Good to know
- A qualification changes nothing on a lot by itself. The lot's rule set must allow it, and each result is accepted on the lot.
- Awaiting approval covers nothing. An Expired qualification still covers lots received within its dates.
- A revocation does not undo accepted results. Assess them under your procedure; the software holds no lot by itself.
- The evidence is never edited. A revoked qualification is final: record a new one.

## Purpose

The evidence that a supplier's certificate results can be relied on for one material and named tests between two dates, its signatures, and every supplier result proposed or accepted under it.

## Who can use it

- Sign-in required. Analyst, Reviewer, Quality, Admin and Auditor roles can open it; users without one of these roles receive 403.
- Action buttons are shown only to Quality users who can use them; the server checks again.
- Admin is read-only here: an account holding only the Admin role can read this page but sees no action buttons, and the server refuses every action (403). Admin plus the Quality role keeps that role's actions; independence rules (no self-review) apply to everyone.

## Layout

- **Header**: breadcrumbs (Suppliers, the supplier's code, SQ-n), title ("supplier code · material code"), the identifier SQ-n and the state label (Awaiting approval, Approved, "Approved, starts later", Expiring soon, Expired or Revoked), action buttons.
- **Notice**: "What a qualification does": "A qualification lets a result the supplier's certificate states stand in for a test only where the lot's rule set allows it, and only through an acceptance signed on the lot." On a revoked qualification with accepted supplier results it is replaced by "Assess the results": "N accepted supplier results relied on this qualification before it was revoked. The revocation does not undo them. Assess them under your procedure: the software records no assessment and holds no lot by itself. A proposal not yet accepted can no longer be signed." ("1 accepted supplier result" for one).
- **Details**: the facts below.
- **Supplier results that relied on this qualification**: Acceptance (links to the record), Lot (links to the lot record), Lot status, Test, Result stated, Certificate, Lot received, State, Proposed by. Above it: "Each row is one result of a supplier's certificate proposed or accepted in place of a test under this qualification, with the lot as it stands now." Empty: "No supplier result has relied on it."
- **Signatures**: signer, meaning, server time, record and bound revision, content hash prefix; "No signatures yet."
- **History**: audit events in order with changes, reasons and actors.

## Actions

| Action | Shown when | Who | Result |
|---|---|---|---|
| **Approve** | Awaiting approval; you did not record it | Quality | Opens the approval signing page. Evidence whose dates lie in the past or the future can be signed |
| **Revoke** | Approved (including Expired and not yet started) | Quality, the recorder included | Opens the revocation signing page |
| Supplier link | Always | Any reader | Opens the supplier record |
| Evidence link | An evidence URL was recorded | Any reader | Opens the external link (`noopener noreferrer`); treat its content as untrusted |
| Acceptance / Lot link | A supplier result relied on the qualification | Any reader | Opens the supplier result acceptance record or the lot record |

## Fields

| Field | Model field | Type / units | Required | Meaning and use |
|---|---|---|---|---|
| Supplier | `SupplierQualification.supplier` | "code · name" | — | The supplier qualified |
| Material | `SupplierQualification.material` | "code · name" | — | The one material the qualification covers |
| Tests covered | `SupplierQualification.test_codes` | "Name (code)", comma separated | — | The tests whose certificate results may be relied on. A code that no specification of the material names any more shows as the code alone |
| Valid from / Valid until (inclusive) | `SupplierQualification.valid_from`, `.valid_until` | Dates | — | A lot is covered when the date it was received lies within them, both days inclusive |
| How the supplier was qualified / Evidence reference / Evidence link | `SupplierQualification.basis`, `.evidence_ref`, `.evidence_url` | Text; text; http(s) link | — | The recorded evidence; "—" when no link was given |
| Recorded by / Recorded | `SupplierQualification.recorded_by`, `.recorded_at` | User, time with zone | — | Who recorded the evidence; that person cannot approve it |
| Approved / Revoked | `SupplierQualification.approved_at`, `.revoked_at` | Time with zone | — | Signing times; "—" until they happen |
| Revision | `SupplierQualification.revision` | Integer | — | Rises by 1 with each signature |
| Acceptance / State / Proposed by | `SupplierResultAcceptance` (SRA-n), `.state`, `.proposed_by` | Link, label, user | — | The proposal or acceptance made under this qualification; Awaiting acceptance, Accepted or Withdrawn, or "No longer stands" for a record of a quarantined lot whose basis has changed |
| Lot / Lot status | `SupplierResultAcceptance.lot` → `Lot.number`, `.state` | Link, text | — | The lot and its status now (Quarantine or Released) |
| Test / Result stated / Certificate / Lot received | `SupplierResultAcceptance.evidence` | Text, date | — | As frozen when the result was proposed: test name and code, the stated result with its unit, the supplier certificate number and the date the lot was received |

## Rules and hidden logic

- **States**: Awaiting approval, then Approved once a second Quality user signs, then Revoked. No other change is possible and a revoked qualification is final: record a new qualification instead.
- **State label**: for an approved record the label follows today's date: "Approved, starts later" before Valid from, Expiring soon within 30 days of Valid until, Expired after it.
- **What it covers**: a supplier result is relied on under this qualification only while it is signed and not revoked, only for a test it names, and only for a lot whose date received lies within its dates. An Expired qualification still covers a lot received within them. A Revoked qualification covers no new proposal and no proposal still awaiting acceptance.
- **Never by itself**: a qualification changes nothing on a lot. The lot's rule set must allow reliance for the test, and each result is proposed by an analyst and accepted by a reviewer on the lot.
- **Results list**: newest proposal first, the latest 50 ("Showing the latest 50 of N." when there are more). It lists proposals awaiting acceptance, accepted results and withdrawn ones, each with its own state.
- **After a revocation**: acceptances already signed stand as signed and stay listed. The supplier result acceptance record shows "Qualification revoked", the lot record shows "Qualification revoked since" and the lot's QC disposition signing page shows a warning. A proposal that was still awaiting acceptance can no longer be signed: its record and the lot record show "No longer stands", and it blocks the lot's QC disposition until it is withdrawn on its record. This list shows it as "No longer stands" too while its lot is in quarantine.
- **Count in the notice**: the number in "Assess the results" counts accepted (signed) records only. Proposals awaiting acceptance and withdrawn records are listed but not counted; with no accepted record the notice stays "What a qualification does".
- **Not enforced by this page**: the software records no assessment of results after a revocation and holds no lot by itself. A revocation does not block the disposition or the certificate of analysis of a lot whose acceptance was already signed. Place a hold from Holds if a lot must not be dispositioned. How often a supplier is re-confirmed is not enforced either; the qualification's end date is the only limit.
- **Assumption**: letting a revoked qualification end further reliance without undoing acceptances already signed is a design default of this product, not a statement of what any regulation requires or permits.
- **Immutable**: the evidence cannot be edited or deleted (database guard); only the state, its times and the revision change, each with a signature.
- Signatures and history are those of this record only. An unknown ID returns 404.

## Related pages

- [Suppliers](/suppliers/)
- Supplier record.
- Approve supplier qualification, Revoke supplier qualification.
- Supplier result acceptance record and lot record (from the list).
- [Holds](/stability/holds/)
