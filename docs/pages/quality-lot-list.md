---
title: Material lots
urls: quality:lot_list
views: quality.views.lot_list
templates: quality/lot_list.html
models: quality.Lot, core.RuleSet
reviewed: 2026-11-10
---

## Purpose

The home page. Lists every manufacturing material lot so you can find a lot, open its record and start a new lot in quarantine.

## Who can use it

- Sign-in required; signed-out visitors go to the sign-in page.
- Viewing requires one of the roles **analyst**, **reviewer**, **quality**, **admin** or **auditor**. Accounts without these roles receive "403 Forbidden" ("Your role does not permit this action.").
- **New material lot** is shown to everyone who can view the list, but only **analysts** can open and submit it; other roles receive 403.

## Layout

- **Header**: title "Material lots", a short description and the **New material lot** button.
- **Search**: one box, "Find lot number", with **Search**.
- **Lots table**: columns Lot, Material, Rule set, Status. Lot numbers link to the lot record.
- **Empty state**: "No material lots found. Receive a lot to start the quality journey." This text also appears when a search matches nothing.
- **Paging**: "Page N of M" with **Previous** and **Next** links.

## Actions

| Action | Shown when | Who | Result |
|---|---|---|---|
| **New material lot** | Always | Analyst | Opens the New material lot form |
| **Search** | Always | Any viewer | Reloads the list filtered by the search text, from page 1 |
| Lot number link | One per row | Any viewer | Opens the lot record |
| **Previous** / **Next** | More than one page | Any viewer | Moves one page; keeps the search text |

## Fields

| Field | Model field | Type / units | Required | Meaning and use |
|---|---|---|---|---|
| Find lot number (`q`) | — | Text | No | Case-insensitive partial match on the lot number only |
| Lot | `Lot.number` | Text, max 80, unique | — | Lot identifier; link to the lot record |
| Material | `Lot.material` | Text, max 160 | — | Material name as received |
| Rule set | `Lot.rules` → `RuleSet.code`, `RuleSet.version` | Shown as "code vN" | — | The approved rule revision chosen at receipt. It is not the lot's specification or sampling requirements, which are assigned afterwards |
| Status | `Lot.state` | Text: Quarantine, Released | — | Quarantine until a signed QC disposition releases the lot |

## Rules and hidden logic

- **Scope**: all lots in every state are listed; there is no status filter and no per-user restriction.
- **Search**: matches anywhere in the lot number (`LOT-TEST` finds `LOT-TEST-001`). Material and rule set are not searched. Leading and trailing spaces are ignored.
- **Order**: newest received first (`Lot.created_at` descending).
- **Paging**: 30 lots per page. An out-of-range page number shows the last page; a non-numeric one shows page 1.
- **Status**: a new lot always starts in **Quarantine**. **Released** is set only by a signed lot disposition. No other states exist in this version.
- **Requirements**: the list does not show whether approved specification and sampling requirements are assigned; open the lot record to see its assignment status.
- **Hidden button rule**: showing **New material lot** does not grant access; the server checks the analyst role.

## Related pages

- New material lot: receive a lot in quarantine.
- Lot record: samples, results, review and disposition.
- [Rule sets](/rules/): approved rule revisions that lots are received under.
