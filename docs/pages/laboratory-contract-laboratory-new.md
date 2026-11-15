---
title: New contract laboratory
urls: laboratory:contract_laboratory_new
views: laboratory.contract_views.contract_laboratory_new
templates: ops/form.html
models: laboratory.ContractLaboratory, core.AuditEvent
reviewed: 2026-11-14
---

## Purpose

Adds an outside laboratory to the register so that approvals can be recorded for it. Adding it approves nothing.

## Who can use it

- Sign-in required. Role: Quality; others receive 403.
- An account holding only the Admin role is refused (403) when it opens or submits this page. Admin plus the Quality role has exactly that role's authority.

## Layout

- Breadcrumbs (Laboratory, Contract laboratories, New contract laboratory), title "New contract laboratory", the introduction "A laboratory's identity cannot be edited after it is added; use synthetic names only. Adding a laboratory approves nothing: record an approval for each method next.", the form in one panel, and a **Cancel** / submit row.

## Actions

| Action | Shown when | Who | Result |
|---|---|---|---|
| **Add contract laboratory** | Always | Quality | Adds the laboratory, shows "Contract laboratory cl-syn-001 added." and opens its record; refusals appear on the form and your entries are kept (status 422) |
| **Cancel** | Always | Quality | Returns to Contract laboratories without saving |

## Fields

| Field | Model field | Type / units | Required | Meaning and use |
|---|---|---|---|---|
| Code | `ContractLaboratory.code` | Slug (letters, numbers, hyphens, underscores), max 60, unique | Yes | Help: "Short stable identifier, e.g. cl-syn-001." Shown on test records and in refusals |
| Name | `ContractLaboratory.name` | Text, max 160 | Yes | Printed on the certificate of analysis for results it reported |
| Location | `ContractLaboratory.location` | Text, max 160 | Yes | Help: "Site that performs the testing: town and country." Printed with the name |
| Reason | `AuditEvent.reason` | Text, max 2000 | Yes | Stored in the audit event |

## Rules and hidden logic

- **Identity only**: the register records who the laboratory is. Results it reports are refused until an approval for the method is recorded and signed by a second Quality user.
- **Code**: "This contract laboratory code already exists." appears beside Code. If another person adds the same code at the same moment, the same message appears above the form and nothing is added. Codes that differ only in upper or lower case are different codes.
- **Spaces**: spaces around the name and location are removed.
- **Immutable**: after it is added the code, name and location cannot be edited or deleted (database trigger). There is no edit, retire or delete action for a laboratory.
- **Audit**: `contract_laboratory.registered` with the code, name, location and your reason. No signature applies to the register.
- **Not enforced by this page**: nothing is checked about the laboratory itself, and one site can be added twice under different codes.
- Assumption: laboratory names should be synthetic in this environment, as the introduction states; the page does not check the content.

## Related pages

- [Contract laboratories](/laboratory/contract-laboratories/)
- Contract laboratory record (opened after saving), where approvals are recorded.
