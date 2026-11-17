---
title: Contract laboratories
urls: laboratory:contract_laboratory_list
views: laboratory.contract_views.contract_laboratory_list
templates: ops/list.html
models: laboratory.ContractLaboratory, laboratory.ContractApproval
reviewed: 2026-11-17
---

## Purpose

Register of the outside laboratories that test for this laboratory, with the approvals each holds today. The register says who a laboratory is; a result it reports is accepted only under a signed approval for the method.

## Who can use it

- Sign-in required. Analyst, Reviewer, Quality, Admin and Auditor roles can open it; users without one of these roles receive 403.
- **New contract laboratory** is shown to Quality only; the server refuses everyone else with 403.
- Admin is read-only here: an account holding only the Admin role can read this page but sees no action buttons, and the server refuses every action (403). Admin plus the Quality role keeps that role's actions; independence rules (no self-review) apply to everyone.

## Layout

- **Section tabs**: Overview, Equipment, Calibrations, Qualifications, Reagents and standards, Contract laboratories, Resource use. These links stay in one row above the header. Scroll sideways when space is limited; the current page is highlighted and brought into view. Anyone who can read Laboratory operations can use every section link.
- **Header**: title and a **New contract laboratory** button for Quality. The introduction is below the title and action row: "Outside laboratories that test for this laboratory, and the methods each is approved for. The register says who a laboratory is. A result it reports is accepted only under an approval for the method, signed by a second quality person."
- **Toolbar**: **Search** (code, name, location, or the method code of any of its approvals; case-insensitive "contains") and **Status** (All, Approval awaiting signature, Approval expiring within 30 days, Approved for a method today, No approval in force today). **Apply** runs the filter; **Clear all** appears when any filter is set. Filters and sort live in the address.
- **Table**: Code (links to the record), Name, Location, Approval (the state of its approval that most needs attention: Expiring soon first, then Approved, "Approved, starts later", Awaiting approval, Expired, Revoked; blank when it has none), Methods approved today, Approvals awaiting signature. Sort by Code (default) or Name. Sortable headers toggle ascending/descending.
- **Footer**: "Showing x–y of N", **Rows per page** (25, 50, 100) and a pager.
- **Empty states**: "No records yet" ("Quality adds a contract laboratory, then records and approves the methods it may perform.", with **New contract laboratory** for Quality); "Nothing matches these filters" with **Clear filters**; "These filters cannot be applied" for an invalid filter value.

## Actions

| Action | Shown when | Who | Result |
|---|---|---|---|
| **New contract laboratory** | Your role can create it | Quality | Opens the New contract laboratory form |
| Code link | Always | Any reader | Opens the contract laboratory record, where approvals are recorded and listed |
| **Apply** / **Clear all** | Always / when a filter is set | Any reader | Reloads the list with or without the filter |
| Column headers, pager, **Show** | Always | Any reader | Sorts, pages or changes rows per page over the whole list |

## Fields

| Field | Model field | Type / units | Required | Meaning and use |
|---|---|---|---|---|
| Search | — | Text, max 100 | No | Matches `ContractLaboratory.code`, `.name`, `.location` or `ContractApproval.method_code` of any approval, whatever its state |
| Status | — | Choice | No | Approval awaiting signature: at least one approval in state Awaiting approval. Approved for a method today: at least one signed, unrevoked approval whose dates include today. Approval expiring within 30 days: such an approval ending today to 30 days ahead. No approval in force today: no signed, unrevoked approval whose dates include today |
| Code / Name / Location | `ContractLaboratory.code`, `.name`, `.location` | Text | — | Identity as registered; it cannot be edited |
| Methods approved today | `ContractApproval.method_code`, `.state`, `.valid_from`, `.valid_until` | Count | — | Methods for which the laboratory holds a signed, unrevoked approval whose dates include today. Two overlapping approvals of one method count once |
| Approvals awaiting signature | `ContractApproval.state` | Count | — | Approvals recorded but not yet signed by a second Quality user |

## Rules and hidden logic

- **Identity only**: a laboratory in this list is not approved for anything by being listed. Each method needs its own approval, recorded by one Quality user and signed by another.
- **Today's view**: the counts and the Status filter use today's date in the deployment time zone; Valid from and Valid until are inclusive days. They say what is in force today, not which reports are accepted: an approval that has run out still covers a report dated within it, so a laboratory under "No approval in force today" may still have reports accepted.
- **Order**: by code unless you sort; ties break on record number. Unknown sort keys fall back to the default.
- Approvals have no list of their own: open the laboratory to see them.

## Related pages

- [Laboratory operations](/laboratory/)
- [New contract laboratory](/laboratory/contract-laboratories/new/)
- Contract laboratory record
