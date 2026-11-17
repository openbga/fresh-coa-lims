---
title: Record contract laboratory approval
urls: laboratory:contract_approval_new
views: laboratory.contract_views.contract_approval_new
templates: ops/form.html
models: laboratory.ContractApproval, laboratory.ContractLaboratory, catalog.Method, core.AuditEvent
reviewed: 2026-11-17
summary: Record the evidence that a contract laboratory may perform one test method between two dates. It approves nothing until a different quality user signs it.
---

## Common tasks
### Record approval evidence
1. Enter [[Method code]] exactly as in the method catalog, and [[Scope]] if the approval has limits.
2. Enter [[Evidence reference]], [[Valid from]] and [[Valid until (inclusive)]], with [[Evidence link]] if there is one.
3. Give a [[Reason]] and select [[Record approval]]. The approval record opens, awaiting approval.
### Leave without recording
1. Select [[Cancel]] to return to the laboratory's record. Nothing is saved.
## Good to know
- The dates are compared with the date of the laboratory's report, not the day the result is recorded.
- One approval covers one method code and every version of that method. Another method or later dates need a new approval.
- Scope is shown with every result that relies on the approval, but the software does not check it.
- You cannot sign approval evidence you recorded. A different quality user must.
- Evidence cannot be edited after recording. Record a new approval instead.

## Purpose

Records the evidence for approving a contract laboratory to perform one test method between two dates. Recording approves nothing: a different Quality user signs it.

## Who can use it

- Sign-in required. Role: Quality; others receive 403.
- An account holding only the Admin role is refused (403) when it opens or submits this page. Admin plus the Quality role has exactly that role's authority, and independence rules (no self-review) still apply.

## Layout

- Breadcrumbs (Laboratory, Contract laboratories, the laboratory's code, Record approval), title "Record approval · cl-syn-001", the introduction "Recording evidence approves nothing. A different quality signer approves it; results are then accepted for reports dated within these dates.", the form in one panel, and a **Cancel** / submit row.

## Actions

| Action | Shown when | Who | Result |
|---|---|---|---|
| **Record approval** | Always | Quality | Saves the evidence as Awaiting approval, shows "Approval evidence recorded; a second quality signer approves." and opens the approval record; refusals appear on the form and your entries are kept (status 422) |
| **Cancel** | Always | Quality | Returns to the contract laboratory record without saving |

## Fields

| Field | Model field | Type / units | Required | Meaning and use |
|---|---|---|---|---|
| Method code | `ContractApproval.method_code` | Text, max 80; must be a code in the method catalog | Yes | Help: "Code of the test method, exactly as in the method catalog. The approval applies to every version of that method." Upper and lower case are ignored; the code is saved as the catalog spells it |
| Scope | `ContractApproval.scope_note` | Text, max 2000 | No | Help: "Limits of the approval, for example the materials it covers. It is shown with every result that relies on the approval; the software does not check it." |
| Evidence reference | `ContractApproval.evidence_ref` | Text, max 200 | Yes | Help: "Quality agreement, audit report or accreditation certificate, with its revision." Shown on test records that rely on the approval |
| Evidence link | `ContractApproval.evidence_url` | http(s) URL, max 500 | No | Untrusted external link |
| Valid from | `ContractApproval.valid_from` | Date | Yes | First report date the approval covers |
| Valid until (inclusive) | `ContractApproval.valid_until` | Date | Yes | Last report date the approval covers; cannot precede Valid from. A date already past is accepted: such evidence can be signed and covers reports dated within it |
| Reason | `AuditEvent.reason` | Text, max 2000 | Yes | Recorded with the evidence |

## Rules and hidden logic

- **One method per approval**: the approval names one method code and covers every version of that method. Another method, or a renewal for later dates, is a new approval. Several approvals of one laboratory and method may exist, with dates that overlap or not.
- **Method code**: a code the method catalog does not hold is refused beside the field: "The method catalog holds no method with this code. Enter the code as it appears under Specifications, Methods."
- **Dates**: "Valid until cannot precede valid from." appears on Valid until when the dates are reversed. The dates are compared with the date of the contract laboratory's report, both days inclusive.
- **Awaiting approval**: the record covers no report until a Quality user other than you signs it. Until then a report dated within it is refused as "still awaiting its signature". Evidence whose Valid until has already passed can still be recorded and approved: it then covers only reports dated within its dates.
- **Immutable**: the evidence cannot be edited or deleted after recording (database guard). To change it, record a new approval; a signed one can be revoked.
- **Audit**: `contract_approval.recorded` with the evidence and your reason. Spaces around the method code, scope and evidence reference are removed.
- **Not enforced by this page**: the method only has to exist in the catalog; whether it has an approved version is not checked. The Scope text is not checked when a report is accepted: it is frozen with each result and shown on the test record for a person to read. The evidence document itself is not read or verified.
- **Assumption**: approving a contract laboratory per method on recorded evidence, with a second Quality signature, is a design default of this product. It is not a statement of what any regulation requires.
- Unknown laboratory: 404.

## Related pages

- Contract laboratory record (Cancel returns here).
- Contract laboratory approval record (opened after saving), where a second Quality user approves.
- [Contract laboratories](/laboratory/contract-laboratories/)
- [Methods](/catalog/methods/) (the method catalog the code must come from).
