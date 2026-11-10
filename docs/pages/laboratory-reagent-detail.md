---
title: Reagent lot record
urls: laboratory:reagent_detail
views: laboratory.views.reagent_detail
templates: ops/record.html
models: laboratory.ReagentLot, laboratory.ResourceUse, core.ElectronicSignature
reviewed: 2026-11-10
---

## Purpose

Provenance, release state, preparations and recorded uses of one lot.

## Who can use it

- Sign-in required. Analyst, Reviewer, Quality, Admin and Auditor roles can open it; users without one of these roles receive 403.
- Action buttons are shown only to roles that can use them; the server checks again.

## Layout

- **Header**: breadcrumbs, title, identifier and status label, action buttons.
- **Details**: the facts below.
- **Preparations from this lot** and **Uses** (latest 25) tables.
- **Signatures**: signer, meaning, server time, record and bound revision, content hash prefix; "No signatures yet."
- **History**: audit events in order with changes, reasons and actors; "No history recorded."

## Actions

| Action | Shown when | Who | Result |
|---|---|---|---|
| **Release for use** | Awaiting release; not recorded by you | Reviewer | Opens the release signing page |
| **Reject lot** | Not already rejected | Analyst, Reviewer, Quality | Opens the reason form |

## Fields

| Field | Model field | Type / units | Required | Meaning and use |
|---|---|---|---|---|
| Kind, Supplier, Supplier lot, dates | `ReagentLot.*` | Text, dates | — | Identity and expiry (last day of use) |
| Assigned purity | `ReagentLot.assigned_purity` | Decimal with unit | — | Certified or assigned value |
| Source lot | `ReagentLot.parent` | Link | — | For prepared solutions |
| Released | `ReagentLot.released_at` | Time | — | Signature time of release |

## Rules and hidden logic

- A rejected lot shows a notice: it and solutions prepared from it cannot be used.

## Related pages

- [Reagents and standards](/laboratory/reagents/)
