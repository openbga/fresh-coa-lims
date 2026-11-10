---
title: Testing: investigations
urls: analytical:investigation_list
views: analytical.views.investigation_list
templates: analytical/investigation_list.html, analytical/_tabs.html, analytical/_pager.html, analytical/_investigation_status.html
models: analytical.Investigation
reviewed: 2026-11-10
---

## Purpose

List out-of-specification investigations. An open investigation holds its lot until quality signs a conclusion.

## Who can use it

- Sign-in required. Viewing requires **analyst**, **reviewer**, **quality**, **admin** or **auditor**; others receive 403.
- No actions that change data.

## Layout

- **Intro**, section tabs (**Tests**, **QC batches**, **Investigations**).
- **Filter bar**: **Find**, **Status** (default **Open**), **Apply**, and **Show open** when a filter differs from the default.
- **Table** (caption "Investigations, newest first"): Investigation, Status, Lot, Test, Trigger, Opened. Footer count and pager.
- **Empty states**: "No open investigations" ("A submitted out-of-specification result opens an investigation automatically.") and "No investigations match".

## Actions

| Action | Shown when | Who | Result |
|---|---|---|---|
| **Apply** / **Show open** | Always / filter differs from default | Any viewer | Applies the filter or returns to open investigations |
| Investigation, Lot and Test links | Each row | Any viewer | Open the investigation, the lot's testing page or the test |

## Fields

| Field | Model field | Type / units | Required | Meaning and use |
|---|---|---|---|---|
| Find | — | Text | No | Matches lot number or test code (case-insensitive) |
| Status (filter) | `Investigation.phase` | Open, Closed, All investigations | No | Open means not closed |
| Status (column) | `Investigation.phase`, `outcome` | Text | — | Phase I open · lot held; Phase II open · lot held; Closed · OOS confirmed; Closed · original invalidated |
| Trigger | `Investigation.trigger` | Text | — | Why it was opened |
| Opened | `Investigation.opened_at` | Date and time | — | When it was opened |

## Rules and hidden logic

- **Default**: only open investigations; any status value other than open or closed shows all.
- **Order and paging**: newest first; 30 per page.
- Investigations are opened by the system when a submitted result is out of specification or when a rejected QC batch had out-of-limit values.

## Related pages

- [Testing: tests](/testing/)
- [Testing: QC batches](/testing/batches/)
- Investigation record, lot testing page.
