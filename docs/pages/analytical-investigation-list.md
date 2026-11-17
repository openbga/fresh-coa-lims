---
title: Testing: investigations
urls: analytical:investigation_list
views: analytical.views.investigation_list
templates: analytical/investigation_list.html, includes/section_tabs.html, includes/pagination.html, analytical/_investigation_status.html
models: analytical.Investigation
reviewed: 2026-11-17
summary: Out-of-specification investigations, open ones by default. An open investigation holds its lot, or its stability pull, until quality signs a conclusion.
---

## Common tasks
### Find an investigation
1. Type a lot number, study identifier or test code in [[Find]].
2. Select [[Apply]], then select an investigation number to open it.
### See closed investigations
1. Choose [[Closed]] or [[All investigations]] in [[Status]], then select [[Apply]].
### Go back to the open investigations
1. Select [[Clear all]].
## Good to know
- The list shows only open investigations unless you choose another status.
- A submitted out-of-specification result, or an out-of-limit value in a rejected QC batch, opens an investigation automatically.
- An investigation of a stability test holds its pull, not the lot. The Lot column then shows the study's lot as plain text.

## Purpose

List out-of-specification investigations. An open investigation holds its lot, or for a stability test its pull, until quality signs a conclusion.

## Who can use it

- Sign-in required. Viewing requires **analyst**, **reviewer**, **quality**, **admin** or **auditor**; others receive 403.
- No actions that change data.
- **Admin** and **auditor** see the same list; it has no scientific actions for any role.

## Layout

- **Section tabs**: **Tests**, **QC batches**, **Investigations**. These links stay in one row above the header. Scroll sideways when space is limited; the current page is highlighted and brought into view.
- **Header**: title "Testing", followed by the introduction.
- **Filter bar**: **Find**, **Status** (default **Open**), **Apply**, and **Clear all** when a search is entered or Status is not Open; it returns to the open investigations.
- **Table** (caption "Investigations, newest first"): Investigation, Status, Lot, Test, Trigger, Opened. Footer: "Showing X–Y of N investigations", with "matching filters" when filtered; **Rows per page** (25, 50 or 100) with **Show**; and, when there is more than one page, first, previous, "Page N of M", next and last page buttons.
- For an investigation of a stability test the Lot column shows the study's lot number as plain text, then a link to the stability pull with the note "stability pull". The investigation belongs to the pull, not to the lot.
- **Empty states**: "No open investigations" ("A submitted out-of-specification result opens an investigation automatically.") and "No investigations match" ("Search covers lot numbers, stability study identifiers and test codes.").

## Actions

| Action | Shown when | Who | Result |
|---|---|---|---|
| **Apply** / **Clear all** | Always / a search is entered or Status is not Open | Any viewer | Applies the filter or returns to open investigations |
| Investigation, Lot and Test links | Each row | Any viewer | Open the investigation, the lot's testing page (or the stability pull) or the test |

## Fields

| Field | Model field | Type / units | Required | Meaning and use |
|---|---|---|---|---|
| Find | — | Text | No | Matches lot number, stability study identifier, the lot number of a stability study, or test code (case-insensitive). Placeholder "Lot, study or test code" |
| Status (filter) | `Investigation.phase` | Open, Closed, All investigations | No | Open means not closed |
| Status (column) | `Investigation.phase`, `outcome` | Text | — | Phase I open · lot held; Phase II open · lot held ("pull held" instead of "lot held" for a stability test); Closed · OOS confirmed; Closed · original invalidated |
| Trigger | `Investigation.trigger` | Text | — | Why it was opened |
| Opened | `Investigation.opened_at` | Date and time | — | When it was opened |

## Rules and hidden logic

- **Default**: only open investigations; any status value other than open or closed shows all.
- **Order and paging**: newest first; 25 rows per page by default, or 50 or 100 through **Rows per page**.
- Investigations are opened by the system when a submitted result is out of specification or when a rejected QC batch had out-of-limit values.

## Related pages

- [Testing: tests](/testing/)
- [Testing: QC batches](/testing/batches/)
- Investigation record, lot testing page.
