---
title: Material lots
urls: quality:lot_list
views: quality.views.lot_list
templates: quality/lot_list.html
models: quality.Lot, quality.LotReceipt, quality.LotDates, suppliers.Supplier, core.RuleSet
reviewed: 2026-11-17
summary: Every material lot in one list. Find a lot, see its status and open its record, or start a new lot in quarantine.
---

## Common tasks

### Find a lot

1. Type a lot, supplier lot or manufacturer lot number in [[Find lot]].
2. To see only lots in one state, choose it in [[Status]].
3. To see lots whose retest or expiry is near or reached, choose an option in [[Dates]].
4. Select [[Apply]], then select a lot number to open its record.

### Start a new lot

1. Select [[New material lot]].
2. Record the receipt details on that page. The new lot starts in Quarantine.

### See every lot again

1. Select [[Clear all]] to remove the search, the status, the queue and the dates.

## Good to know

- Search covers lot numbers and the supplier and manufacturer lot numbers of the current receipt details. It does not search material or supplier names.
- The newest lot record comes first, not the lot received most recently.
- Only a signed decision on the lot record moves a lot out of Quarantine.
- The Dates filter covers lots in Quarantine or Released only. A Rejected or Cancelled lot never shows as Retest due or Expired.
- The list does not show whether requirements are assigned. Open the lot record to see it.

## Purpose

Lists every manufacturing material lot so you can find a lot, open its record and start a new lot in quarantine.

## Who can use it

- Sign-in required; signed-out visitors go to the sign-in page.
- Viewing lot data requires one of the roles **analyst**, **reviewer**, **quality**, **admin** or **auditor**. On opening the list, signed-in accounts without these roles are sent to [Account access](/accounts/access/), which explains missing roles. Superuser status does not bypass this check.
- **New material lot** is shown only to **analysts**. Admin-only and other viewers cannot open or submit it; direct requests receive 403.

## Layout

- **Shared top bar**: the certificate-and-leaf mark and **OpenBGA QM LIMS** name link to the Dashboard. Menu opens navigation; on phones it is an icon named "Menu". Theme, your name with your laboratory roles (for example "Synthetic Analyst · Analyst"; several roles are comma-separated), Sign out and Page documentation remain available at the right. On a phone the brand text shortens visually to **QM LIMS**, and your name and roles open the Account section of the menu instead.
- **Header**: title "Material lots" and the **New material lot** button for analysts, with a short description below.
- **Toolbar** (at the top of the table card): the labelled **Find lot** box (placeholder "Lot, supplier lot or manufacturer lot"), the **Status** selector (All lots, Quarantine, Released, Rejected, Cancelled), the **Queue** selector (Any queue, or one of the Dashboard's lot queues: Requirements not assigned, Applicability hold, Supplier certificate not recorded, Awaiting sampling, Samples without assigned tests, Supplier results awaiting acceptance, All results reviewed, Blocked by an investigation, Certificates to issue), the **Dates** selector (Any dates, Retest due, Expired, Retest or expiry within 30 days), **Apply**, and **Clear all** when a search, status, queue or dates option is set.
- **Lots table**: columns Lot, Status, Material (with its kind icon when the lot's requirements name a catalog material), Supplier (the supplier lot number below it, or "Supplier lot not known"), Received, Where it is, Retest date, Expiry date, Rule set. Lot numbers link to the lot record; status has a text label and icon, followed by "Applicability hold" when the lot's requirements are on hold and the phase of an open investigation ("Phase I laboratory investigation", "Phase II full investigation") and, for a Quarantine or Released lot, "Retest due" or "Expired" when its dates in force say so. A lot without receipt details shows "Receipt not recorded" under Supplier and "—" under Received. **Columns** chooses which columns show and their order, saved for your account; Retest date, Expiry date and Rule set, then Supplier and Received, are hidden by default when the table does not fit its panel; a saved layout always wins.
- **Empty states**: "No material lots yet" with "Receive a lot to start the quality journey." Analysts also see **New material lot**. A search with no matches shows "No material lots match these filters", "Search covers lot numbers and the supplier and manufacturer lot numbers of the current receipt details. Change the search, the status or the dates, or clear the filters." and **Clear filters**.
- **Source code**: the shared application footer links to the source repository configured for this deployment, [openbga/qm-lims](https://github.com/openbga/qm-lims) by default.
- **Footer**: "Showing X–Y of N material lots", with "matching filters" when searched; **Rows per page** (25, 50 or 100) with **Show**; and, when there is more than one page, first, previous, "Page N of M", next and last page buttons; unavailable directions are disabled.

## Actions

| Action | Shown when | Who | Result |
|---|---|---|---|
| **New material lot** | Analyst role | Analyst | Opens the New material lot form |
| **Source code** | Always | Any viewer | Opens the configured source repository |
| **Apply** | Always | Any viewer | Reloads the list filtered by the search text, status, queue and dates option, from page 1 |
| **Clear all** | A search, status, queue or dates option is set | Any viewer | Removes the search, the status, the queue and the dates and returns to the first page |
| **Clear filters** | A search, status, queue or dates option matches no lot (in the empty state) | Any viewer | Same as **Clear all** |
| **Rows per page** / **Show** | At least one lot is listed | Any viewer | Shows 25, 50 or 100 lots per page from page 1, keeping the search and status |
| Lot number link | One per row | Any viewer | Opens the lot record |
| First / previous / next / last page | More than one page; enabled when that direction exists | Any viewer | Moves to that page; keeps the search text, status and rows per page |

## Fields

| Field | Model field | Type / units | Required | Meaning and use |
|---|---|---|---|---|
| Status (`state`) | `Lot.state` | Choice | No | Shows only lots in that state; an unknown value is ignored and the other filters still apply |
| Queue (`queue`) | derived (`quality/dashboard.py`) | Choice | No | Shows only the lots waiting in that Dashboard queue, by the same conditions the Dashboard counts, so the Dashboard count equals the rows listed; an unknown value is ignored |
| Dates (`dates`) | `LotDates.expiry_on`, `retest_on` | Choice | No | Any dates (no filter); Retest due: lots in Quarantine or Released whose retest date is today or earlier and whose expiry date is not past; Expired: lots in Quarantine or Released whose expiry date is before today; Retest or expiry within 30 days: lots in Quarantine or Released with neither date reached and one of them within the next 30 days. Local date; an unknown value is ignored |
| Rows per page (`per_page`) | — | Choice: 25, 50, 100 | No | Lots per page; default 25 |
| Find lot (`q`) | — | Text | No | Case-insensitive partial match on the lot number, or on the supplier lot number or manufacturer lot number of the lot's current receipt details |
| Lot | `Lot.number` | Text, max 80, unique | — | Lot identifier; link to the lot record |
| Material | `Lot.material` | Text, max 160 | — | Material name as received |
| Supplier | `LotReceipt.supplier` → `Supplier.name`, else `LotReceipt.source` | Text | — | Name of the supplier on the current receipt details; "Made on site" for a lot made on site |
| Supplier lot | `LotReceipt.supplier_lot` | Text, max 80 | — | Supplier lot number on the current receipt details; "Not known" when the supplier's lot number is blank, "—" for a lot made on site |
| Received | `LotReceipt.received_on` | Date | — | Date received on the current receipt details |
| Where it is | derived (`quality/route.py`) | Six-step route and one line | — | Where the lot is in the QC flow, from recorded data only: requirements (Not assigned, Applicability hold), samples, results entered and reviewed ("3 of 6 entered", "5 of 7 reviewed"), the decision (Released, Rejection signed, Investigation open) and the certificate (Certificate issued, Not issued); a cancelled lot shows "Received in error". The route graphic repeats the text and is hidden from screen readers |
| Retest date | `LotDates.retest_on` | Date | — | The retest date in force; "—" when none |
| Expiry date | `LotDates.expiry_on` | Date | — | The expiry date in force; "—" when none |
| Rule set | `Lot.rules` → `RuleSet.code`, `RuleSet.version` | Shown as "code vN" | — | The approved rule revision chosen at receipt. It is not the lot's specification or sampling requirements, which are assigned afterwards |
| Status | `Lot.state` | Text: Quarantine, Released, Rejected, Cancelled | — | Quarantine until a signed decision ends it: release (disposition), rejection, or cancellation as received in error. Cancelled shows the tooltip "Received in error". A Quarantine or Released lot also shows "Retest due" (retest date reached, from that day on) or "Expired" (after the expiry date) beside it |

## Rules and hidden logic

- **Scope**: all lots in every state are listed unless the Status or Queue selector narrows them; there is no per-user restriction.
- **Search**: matches anywhere in the lot number (`LOT-TEST` finds `LOT-TEST-001`), or anywhere in the supplier lot number or manufacturer lot number of the lot's current receipt details. Receipt records replaced by a correction are not searched. Supplier name, material and rule set are not searched. Leading and trailing spaces are ignored.
- **Receipt columns**: Supplier, Supplier lot and Received come from the lot's current receipt details, the record that no correction has replaced. The manufacturer lot number is searched but not shown; open the lot record to see it.
- **Receipt not recorded**: shown for a lot received before receipt details were kept. An analyst can record them from the lot record while the lot is in Quarantine.
- **Order**: newest lot record first (`Lot.created_at` descending), not by the Received date.
- **Paging**: 25 lots per page by default; **Rows per page** accepts 25, 50 or 100, and any other value shows 25. An out-of-range page number shows the last page; a non-numeric one shows page 1.
- **Status**: a new lot always starts in **Quarantine**. **Released**, **Rejected** and **Cancelled** are set only by signed decisions on the lot record.
- **Requirements**: the list does not show whether approved specification and sampling requirements are assigned; open the lot record to see its assignment status.
- **Role rule**: the creation button is hidden without the analyst role, and the server independently checks that role.

## Related pages

- [Dashboard](/): where lots and their tests wait in the QC flow.
- New material lot: receive a lot in quarantine with its receipt details.
- Lot record: receipt details, samples, results, review and disposition.
- [Suppliers](/suppliers/): the register that receipt details name suppliers from.
- [Rule sets](/rules/): approved rule revisions that lots are received under.
