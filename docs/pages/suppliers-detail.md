---
title: Supplier record
urls: suppliers:detail
views: suppliers.views.supplier_detail
templates: suppliers/detail.html
models: suppliers.Supplier, suppliers.SupplierQualification, catalog.Material, quality.LotReceipt, quality.Lot, core.AuditEvent
reviewed: 2026-11-17
---

## Purpose

Shows one supplier's identity, its qualifications, the lots whose current receipt details name it, and the history of the supplier record.

## Who can use it

- Sign-in required. Viewing requires one of **analyst**, **reviewer**, **quality**, **admin** or **auditor**; others receive 403 Forbidden.
- **Record qualification**: **quality** role only; hidden for others, who receive 403 Forbidden if they open that page directly. **admin** without the quality role does not see it.
- The supplier itself is read-only for every role: it has no edit, retire or delete action.

## Layout

- **Breadcrumbs**: Suppliers, supplier code. Title: the supplier code, with the supplier name below it. **Record qualification** button for quality.
- **Supplier** card: Code, Name, Location and Created (date, time and time zone, then "by" and the user who added it).
- **Qualifications** card: the text "The register says who a supplier is. A qualification is the signed evidence that the supplier's certificate results can be relied on for one material and the tests it names. It takes effect only where the lot's rule set allows it and through an acceptance signed on the lot.", then a table with Qualification, Material, Tests covered, Valid from, Valid until (inclusive), Evidence and State. Empty: "No qualification is recorded. Results on this supplier's certificates are recorded on each lot and do not stand in for a test."
- **Lots received** card: table with Lot, Status, Material, Supplier lot, Manufacturer lot, Received and Quantity. Footer "Showing X–Y of N lots", **Rows per page** (25, 50 or 100) with **Show**, and first, previous, "Page N of M", next and last page buttons when there is more than one page. Empty: "No lots received from this supplier" ("Lots appear here when their current receipt details name this supplier.").
- **History** card: the audit events of the supplier record, oldest first, each with the event name (`supplier.created`), time, reason and user. "No recorded history." when there are none.
- **Foot line**: the supplier code, then "Viewed" with the time and your name.

## Actions

| Action | Shown when | Who | Result |
|---|---|---|---|
| **Record qualification** | Quality role | Quality | Opens Record supplier qualification for this supplier |
| Qualification link (SQ-n) | One per qualification | Any viewer | Opens the supplier qualification record |
| Lot number link | One per row | Any viewer | Opens the lot record |
| **Suppliers** (breadcrumb) | Always | Any viewer | Returns to the register |
| **Previous** / **Next** | More than one page of lots | Any viewer | Moves one page |

## Fields

| Field | Model field | Type / units | Required | Meaning and use |
|---|---|---|---|---|
| Code | `Supplier.code` | Text | — | Identifier; also the page title. |
| Name | `Supplier.name` | Text | — | Supplier name. |
| Location | `Supplier.location` | Text | — | Site the material is supplied from. |
| Created | `Supplier.created_at`, `Supplier.created_by` | Date and time; user | — | Full name, or the username when no name is set. |
| Qualification | `SupplierQualification` (SQ-n) | Link | — | Identifier of the qualification; opens its record. |
| Material | `SupplierQualification.material` | "code · name" | — | The one material the qualification covers. |
| Tests covered | `SupplierQualification.test_codes` | "Name (code)", comma separated | — | The tests whose certificate results may be relied on. A code that no specification of the material names any more shows as the code alone. |
| Valid from / Valid until (inclusive) | `SupplierQualification.valid_from`, `valid_until` | Dates | — | A lot is covered when the date it was received lies within them, both days inclusive. |
| Evidence | `SupplierQualification.evidence_ref` | Text | — | Reference of the qualification report, audit report or comparison record. |
| State | `SupplierQualification.state`, `valid_from`, `valid_until` | Label | — | Awaiting approval, Approved, "Approved, starts later", Expiring soon (within 30 days of Valid until), Expired or Revoked. For an approved record the label follows today's date. |
| Lot | `LotReceipt.lot` → `Lot.number` | Link | — | Lot received from this supplier. |
| Status | `Lot.state` | Quarantine, Released, Rejected, Cancelled | — | Current lot status. |
| Material | `Lot.material` | Text | — | Material name as received. |
| Supplier lot | `LotReceipt.supplier_lot` | Text | — | "Not known" when blank. |
| Manufacturer lot | `LotReceipt.manufacturer_lot` | Text | — | "—" when blank. |
| Received | `LotReceipt.received_on` | Date | — | Date received. |
| Quantity | `LotReceipt.quantity`, `LotReceipt.quantity_unit` | Decimal with unit | — | Exact quantity received, without trailing zeros. |
| History entry | `AuditEvent.action`, `occurred_at`, `reason`, `actor` | Text, date and time, user | — | What happened to the supplier record, when, why and by whom. |

## Rules and hidden logic

- **Qualifications listed**: every qualification of this supplier, whatever its state, latest Valid from first; qualifications with the same Valid from are ordered latest recorded first. The list is not paged. A supplier may hold several qualifications, also for one material.
- **What a qualification does**: only a qualification that is signed and not revoked is relied on, only for the material and tests it names and for a lot received within its dates. Awaiting approval and Revoked records cover nothing. An Expired one still covers a lot received within its dates.
- **Lots listed**: one row per lot whose current receipt details name this supplier. A receipt record that a correction replaced is not used, so a lot corrected to another supplier, or to "Made on site", leaves this list. The replaced record stays in the Receipt history on the lot record.
- **Order**: latest date received first; lots received on the same date are ordered latest recorded first.
- **Paging**: 25 lots per page by default; **Rows per page** (or `per_page`) chooses 25, 50 or 100.
- **History**: shows events of the supplier record only. Receipt events of the lots are on each lot record and in the Audit trail. The history of a qualification is on its own record.
- **Immutable**: the code, name and location cannot be edited or deleted (database trigger).
- **Not enforced by this page**: being listed here, or holding a qualification, does not by itself change which tests a lot requires or what its disposition needs. A supplier result stands in for a test only where the lot's rule set allows it and an acceptance is signed on the lot. How often a supplier is re-confirmed is not enforced; a qualification's end date is the only limit.
- Unknown supplier: 404.

## Related pages

- [Suppliers](/suppliers/)
- Record supplier qualification; Supplier qualification record.
- Lot record (from a lot number).
- [Audit trail](/audit/)
