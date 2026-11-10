---
title: New reagent lot
urls: laboratory:reagent_new
views: laboratory.views.reagent_new
templates: ops/form.html
models: laboratory.ReagentLot, core.AuditEvent
reviewed: 2026-11-10
---

## Purpose

Record a received reagent or standard lot, or a prepared solution, with its provenance.

## Who can use it

- Sign-in required. Roles: Analyst or Quality; others receive 403.

## Layout

- Breadcrumbs (Laboratory, Reagents and standards, New reagent lot), title, the introduction "A lot cannot be used until a different reviewer signs its release. A prepared solution needs a released source lot and cannot outlive it.", the form in one panel, and a **Cancel** / submit row.

## Actions

| Action | Shown when | Who | Result |
|---|---|---|---|
| **Record lot** | Always | Analyst or Quality; others receive 403 | Saves and opens the new lot with "Lot recorded; independent release needed before use."; domain refusals appear as an error summary and your entries are kept (status 422) |
| **Cancel** | Always | Any | Returns without saving |

## Fields

| Field | Model field | Type / units | Required | Meaning and use |
|---|---|---|---|---|
| Identifier | `ReagentLot.identifier` | Text, max 60, unique | Yes | Your internal ID |
| Kind | `ReagentLot.kind` | Reagent / Reference standard / Prepared solution | Yes | Prepared solutions need a source lot |
| Name, Supplier, Lot number | `ReagentLot.name`, `.supplier`, `.lot_number` | Text, max 160 / 160 / 80 | Name, Lot number | Identity and supplier lot; Supplier is optional |
| Received or prepared on | `ReagentLot.received_on` | Date | Yes | Receipt or preparation date |
| Expiry date (last day of use) | `ReagentLot.expiry_date` | Date | Yes | Not before the received date (database check); for a prepared solution not after the source's expiry |
| Assigned purity / Purity unit | `ReagentLot.assigned_purity`, `.purity_unit` | Decimal, 0 or more, up to 12 digits with 6 decimals; unit text, max 20 (for example % w/w) | Together or neither | "Give the purity and its unit together." |
| Parent | `ReagentLot.parent` | Choice of released lots, by identifier | Prepared solutions only | Source lot; refused for other kinds |
| Preparation note | `ReagentLot.preparation_note` | Text | No | Diluent, amounts, calculation |
| Certificate ref / url | `ReagentLot.certificate_ref`, `.certificate_url` | Text, max 200; http(s) link, max 500 | No | Controlled external evidence |
| Reason | `AuditEvent.reason` | Text, max 2000 | Yes | Recorded with the event |

## Rules and hidden logic

- Messages: "A prepared solution needs its source lot."; "The source lot must be released for use and still eligible: …" followed by the reasons; "A prepared solution cannot outlive its source lot."; "Only a prepared solution has a source lot."; "Receipt or preparation cannot be dated in the future.".
- The source lot and every lot it was prepared from must be released and eligible (not rejected, not expired).
- The lot starts Awaiting release and cannot be used until a different reviewer signs its release. Provenance fields cannot be edited. Event `reagent.received`.

## Related pages

- [Reagents and standards](/laboratory/reagents/)
