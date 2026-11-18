---
title: Contract laboratory record
urls: laboratory:contract_laboratory_detail
views: laboratory.contract_views.contract_laboratory_detail
templates: ops/record.html
models: laboratory.ContractLaboratory, laboratory.ContractApproval, laboratory.ContractUse, core.AuditEvent
reviewed: 2026-11-17
summary: One contract laboratory: its identity, its approvals by method and the results that relied on it. Record approval evidence for a method here.
---

## Common tasks
### Record an approval for a method
1. Select [[Record approval]]. It shows only for the quality role.
2. Enter the method, dates and evidence on that page. A second quality user then signs it.
### Approve or revoke an approval
1. In [[Approvals by method]], select the approval number to open it.
2. Select [[Approve]] or [[Revoke]] on that page and sign with your PIN.
### Assess what a laboratory's results affected

1. Select [[More]] then [[Assess impact]]. It shows to the quality role only.
2. Set the period on the form that opens; the tests it reported in that period are found.

### See results that relied on the laboratory
1. See [[Results that relied on this laboratory]]. Select a work entry to open the test.
## Good to know
- This record approves nothing. A report is accepted only under a signed, unrevoked approval for the method whose dates include the report date.
- An Expired approval still covers reports dated within its dates. A Revoked one covers no new report.
- The results list shows each test as it stands now, newest first, up to the latest 50.
- The code, name and location cannot be edited.
- Signatures are kept on each approval, not on the laboratory record.

## Purpose

One outside laboratory: who it is, the approvals it holds for each method, and the results that relied on them.

## Who can use it

- Sign-in required. Analyst, Reviewer, Quality, Admin and Auditor roles can open it; users without one of these roles receive 403.
- **Record approval** is shown to Quality only; the server checks again.
- Admin is read-only here: an account holding only the Admin role can read this page but sees no action buttons, and the server refuses every action (403). Admin plus the Quality role keeps that role's actions; independence rules (no self-review) apply to everyone.

## Layout

- **Header**: breadcrumbs, title (the laboratory's name), its code and the label "Identity only", action button.
- **Details**: the facts below.
- **Approvals by method**: Approval (CLA-n, links to the approval), Method, Valid from, Valid until (inclusive), Evidence, State. Above it: "The register says who a laboratory is. A result it reports is accepted only under an approval for the method, signed by a second quality person." Empty: "No approval is recorded. Results from this laboratory are refused until an approval for the method is signed."
- **Results that relied on this laboratory**: Accepted, Work (links to the test), Lot, Test, State, Reportable result, Report, Report dated, Approval (links to it), By. Above it: "Each row is one report accepted into a test record, with the test as it stands now. A correction that names another laboratory or another report is a new acceptance and adds a row." Empty: "No result has relied on it."
- **Signatures**: "No signatures yet." The register has no signed step; signatures are on each approval.
- **History**: audit events of this record with reasons and actors.

## Actions

| Action | Shown when | Who | Result |
|---|---|---|---|
| **Record approval** | Always | Quality | Opens the Record approval form for this laboratory |
| **Assess impact** (under **More**) | Quality role | Quality | Opens New impact assessment with this laboratory chosen. Changes nothing on this record |
| Approval link (CLA-n) | An approval exists | Any reader | Opens the approval record, where it is approved or revoked |
| Work link | A result relied on the laboratory | Any reader | Opens the test record |

## Fields

| Field | Model field | Type / units | Required | Meaning and use |
|---|---|---|---|---|
| Code / Name / Location | `ContractLaboratory.code`, `.name`, `.location` | Text | — | Identity as registered; it cannot be edited |
| Added by / Added | `ContractLaboratory.created_by`, `.created_at` | User, time with zone | — | Who added the laboratory and when |
| Approval / Method | `ContractApproval` number, `.method_code` | CLA-n, text | — | One row per approval, by method code and then newest Valid from first |
| Valid from / Valid until (inclusive) / Evidence | `ContractApproval.valid_from`, `.valid_until`, `.evidence_ref` | Dates, text | — | The dates a report must fall within, and the evidence reference |
| State | `ContractApproval.state`, `.valid_from`, `.valid_until` | Label | — | Awaiting approval, Approved, "Approved, starts later" (Valid from is after today), Expiring soon (ends within 30 days), Expired (past Valid until) or Revoked |
| Accepted / By | `ContractUse.used_at`, `.used_by` | Time with zone, user | — | When the report was accepted into the test record, and by whom |
| Work / Lot / Test / State / Reportable result | `ContractUse.context_id`, `AnalyticalTest` | Text | — | The test ("T-n · lot · sample"), its lot, test code, state and reportable result as they stand now |
| Report / Report dated | `ContractUse.report_number`, `.report_date` | Text, date | — | The contract laboratory's report as entered |

## Rules and hidden logic

- **Identity only**: this record approves nothing. A report from the laboratory is accepted only under an approval for the test's method that is signed, not revoked, and whose dates include the date of the report.
- **Expired is not revoked**: an Expired approval still covers a report dated within its dates. A Revoked approval covers nothing.
- **Results list**: newest first, the latest 50 ("Showing the latest 50 of N." when there are more). It is append-only: rows are never changed or removed. A correction that keeps the laboratory and the report adds no row; one that names another laboratory or report adds one.
- **Immutable**: the code, name and location cannot be edited or deleted (database trigger). There is no edit, retire or delete action.
- History shows `contract_laboratory.registered`; approvals keep their own signatures and history. An unknown ID returns 404.

## Related pages

- [Contract laboratories](/laboratory/contract-laboratories/)
- Record approval, Contract laboratory approval record.
- Test record (from a Work link).
