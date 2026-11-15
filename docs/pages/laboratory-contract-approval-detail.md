---
title: Contract laboratory approval record
urls: laboratory:contract_approval_detail
views: laboratory.contract_views.contract_approval_detail
templates: ops/record.html
models: laboratory.ContractApproval, laboratory.ContractLaboratory, laboratory.ContractUse, core.ElectronicSignature, core.AuditEvent
reviewed: 2026-11-14
---

## Purpose

The evidence that a contract laboratory may perform one test method between two dates, its signatures, and every result that relied on it.

## Who can use it

- Sign-in required. Analyst, Reviewer, Quality, Admin and Auditor roles can open it; users without one of these roles receive 403.
- Action buttons are shown only to Quality users who can use them; the server checks again.
- Admin is read-only here: an account holding only the Admin role can read this page but sees no action buttons, and the server refuses every action (403). Admin plus the Quality role keeps that role's actions; independence rules (no self-review) apply to everyone.

## Layout

- **Header**: breadcrumbs, title ("laboratory code · method code"), the identifier CLA-n and the state label (Awaiting approval, Approved, "Approved, starts later", Expiring soon, Expired or Revoked), action buttons.
- **Notice** (revoked approval with results): "Assess the results": "N accepted reports relied on this approval before it was revoked. Each result stands as recorded. Assess them under your procedure: the software records no assessment and holds no lot by itself." ("1 accepted report" for one).
- **Details**: the facts below.
- **Results that relied on this approval**: Accepted, Work (links to the test), Lot, Test, State, Reportable result, Report, Report dated, By. Above it: "Each row is one report accepted into a test record, with the test as it stands now. A correction that names another laboratory or another report is a new acceptance and adds a row." Empty: "No result has relied on it."
- **Signatures**: signer, meaning, server time, record and bound revision, content hash prefix; "No signatures yet."
- **History**: audit events in order with changes, reasons and actors.

## Actions

| Action | Shown when | Who | Result |
|---|---|---|---|
| **Approve** | Awaiting approval; you did not record it | Quality | Opens the approval signing page. Evidence whose Valid until has passed can still be signed, for reports dated within its dates |
| **Revoke** | Approved (including Expired and not yet started) | Quality, the recorder included | Opens the revocation signing page |
| Laboratory link | Always | Any reader | Opens the contract laboratory record |
| Evidence link | An evidence URL was recorded | Any reader | Opens the external link (`noopener noreferrer`); treat its content as untrusted |
| Work link | A result relied on the approval | Any reader | Opens the test record |

## Fields

| Field | Model field | Type / units | Required | Meaning and use |
|---|---|---|---|---|
| Laboratory | `ContractApproval.laboratory` | "code · name" | — | The laboratory approved |
| Method | `ContractApproval.method_code` | Text | — | The method code approved, as the method catalog spells it; every version of the method, upper and lower case ignored |
| Valid from / Valid until (inclusive) | `ContractApproval.valid_from`, `.valid_until` | Dates | — | A report is covered when its date lies within them, both days inclusive |
| Evidence reference / Evidence link / Scope | `ContractApproval.evidence_ref`, `.evidence_url`, `.scope_note` | Text; http(s) link; text | — | Controlled evidence and its limits; "—" when not given. The Scope is shown with every result that relies on the approval and is not checked by the software |
| Recorded by / Recorded | `ContractApproval.recorded_by`, `.recorded_at` | User, time with zone | — | Who recorded the evidence; that person cannot approve it |
| Approved / Revoked | `ContractApproval.approved_at`, `.revoked_at` | Time with zone | — | Signing times; "—" until they happen |
| Revision | `ContractApproval.revision` | Integer | — | Rises by 1 with each signature |
| Accepted / By | `ContractUse.used_at`, `.used_by` | Time with zone, user | — | When a report was accepted under this approval, and by whom |
| Work / Lot / Test / State / Reportable result | `ContractUse.context_id`, `AnalyticalTest` | Text | — | The test ("T-n · lot · sample"), its lot, test code, state and reportable result as they stand now |
| Report / Report dated | `ContractUse.report_number`, `.report_date` | Text, date | — | The contract laboratory's report as entered |

## Rules and hidden logic

- **States**: Awaiting approval, then Approved once a second Quality user signs, then Revoked. No other change is possible and a revoked approval is final: record a new approval instead.
- **State label**: for an approved record the label follows today's date: "Approved, starts later" before Valid from, Expiring soon within 30 days of Valid until, Expired after it.
- **What it covers**: a report is accepted under this approval only while it is signed and not revoked, and only when the date of the report lies within its dates. An Expired approval still covers a report dated within them. A Revoked approval covers no new report, also for report dates before the revocation; a result already recorded under it can still be corrected when its laboratory and report stay the same.
- **Results list**: newest first, the latest 50 ("Showing the latest 50 of N." when there are more). It is append-only. A correction that keeps the laboratory and the report adds no row; one that names another laboratory or report is a new acceptance and adds one. After a revocation the rows stay and the notice asks quality to assess them; each test record and its Sign review page show an "Approval revoked" notice, and the lot's QC disposition signing page shows a warning.
- **Not enforced by this page**: the software records no assessment of results after a revocation and holds no lot by itself. A revocation does not block the review, the disposition or the certificate of those results. Place a hold from Holds if a lot must not be dispositioned.
- **Immutable**: the evidence cannot be edited or deleted (database guard); only the state, its times and the revision change, each with a signature.
- Signatures and history are those of this record only. An unknown ID returns 404.

## Related pages

- [Contract laboratories](/laboratory/contract-laboratories/)
- Contract laboratory record.
- Approve contract laboratory approval, Revoke contract laboratory approval.
- Test record (from a Work link).
- [Holds](/stability/holds/)
