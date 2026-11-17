---
title: Suppliers
urls: suppliers:list
views: suppliers.views.supplier_list
templates: suppliers/list.html
models: suppliers.Supplier, quality.LotReceipt
reviewed: 2026-11-17
summary: The supplier register: the companies lots are received from. Find a supplier, see its best qualification state and lots received, and open its record. Quality users add suppliers.
---

## Common tasks
### Find a supplier
1. Type a code, name or location in [[Search]], then select [[Apply]].
2. Select a supplier code to open its record.
### Add a supplier
1. Select [[New supplier]]. Only quality users see it.
### See every supplier again
1. Select [[Clear all]] to remove the search.
## Good to know
- Being in the register does not qualify a supplier or reduce testing. A qualification is a separate signed record on the supplier's page.
- Qualification shows the supplier's best state across its qualifications. Each covers one material and named tests; open the supplier for detail.
- Lots received counts only current receipt details. A lot corrected to another supplier moves to that supplier's count.
- A supplier cannot be edited or deleted after it is added.

## Purpose

The supplier register: the companies that lots are received from. The receipt details of a lot received from a supplier name one supplier from this register. The register records identity only; a supplier's qualifications are separate signed records on its supplier record.

## Who can use it

- Sign-in required. Viewing requires one of **analyst**, **reviewer**, **quality**, **admin** or **auditor**; others receive 403 Forbidden.
- **New supplier**: **quality** role only; hidden for others, who receive 403 Forbidden if they open the form directly.
- **admin** without the quality role can view the register but sees no **New supplier** button.

## Layout

- **Sidebar**: **Suppliers** is in the **Configuration** section, between Specifications and Rule sets.
- **Header**: title "Suppliers" and the **New supplier** button for quality, with the introduction below.
- **Intro**: "Companies that lots are received from. The register records who a supplier is; it does not qualify a supplier or reduce testing. A qualification is a separate signed record on the supplier's page."
- **Filter bar**: **Search** (placeholder "Code, name or location"), **Apply**, **Clear all** when a search is set.
- **Table**: Supplier (code), Name, Location, Qualification, Lots received (count), Created (date). Supplier and Name headers sort.
- **Footer**: "Showing X–Y of N suppliers", with "matching filters" when filtered; **Rows per page** (25, 50 or 100) with **Show**; and, when there is more than one page, first, previous, "Page N of M", next and last page buttons.
- **Empty states**: "No suppliers yet" ("A lot received from a supplier names one from this register. A quality user adds the first supplier.") with **New supplier** for quality; "No suppliers match these filters" ("Search covers codes, names and locations. Change or clear the filters.") with **Clear filters**.

## Actions

| Action | Shown when | Who | Result |
|---|---|---|---|
| **New supplier** | Quality role | Quality | Opens the New supplier form |
| Supplier code link | One per row | Any viewer | Opens the supplier record |
| **Apply** | Always | Any viewer | Reloads the list with the search, from page 1, keeping the sort |
| **Clear all** | A search is set | Any viewer | Removes the search and returns to the default order |
| Supplier / Name header | Table shown | Any viewer | Sorts ascending; activating the sorted header again reverses it |
| **Previous** / **Next** | More than one page | Any viewer | Moves one page; keeps the search and sort |

## Fields

| Field | Model field | Type / units | Required | Meaning and use |
|---|---|---|---|---|
| Search (`q`) | — | Text | No | Case-insensitive contains match on code, name or location. Leading and trailing spaces are ignored. |
| Supplier | `Supplier.code` | Text | — | Identifier; link to the supplier record. |
| Name | `Supplier.name` | Text | — | Supplier name. |
| Location | `Supplier.location` | Text | — | Site the material is supplied from. |
| Qualification | `SupplierQualification.state`, `.valid_from`, `.valid_until` | Label | — | The supplier's best qualification state, in this order: Approved, Expiring soon, "Approved, starts later", Awaiting approval, Expired, Revoked; "—" when none is recorded. A qualification covers one material and named tests: open the supplier for the detail. |
| Lots received | — | Count | — | Lots whose current receipt details name this supplier. |
| Created | `Supplier.created_at` | Date | — | Date the supplier was added. |

## Rules and hidden logic

- **Order**: code ascending by default. Sort keys: code and name, each ascending or descending; equal names are ordered by code.
- **Paging**: 25 rows per page by default; **Rows per page** (or `per_page`) chooses 25, 50 or 100; other values fall back to 25.
- **Lots received**: counts only current receipt details. A receipt record that a correction replaced is not counted, so a lot corrected to another supplier moves from one count to the other.
- **Immutable**: a supplier cannot be edited or deleted after creation (database trigger). There is no edit, retire or delete action.
- **Qualification column**: one state per supplier, the best of its qualifications across all materials. Open the supplier record to see each qualification, the material and tests it covers, and to record one.
- **Not enforced by this page**: being in the register does not qualify a supplier. Naming a supplier on a lot's receipt does not by itself change which tests the lot requires or what its disposition needs; a supplier result stands in for a test only under a signed qualification, where the lot's rule set allows it, through an acceptance signed on the lot.

## Related pages

- New supplier.
- Supplier record (qualifications are recorded and listed there).
- [Material lots](/lots/)
