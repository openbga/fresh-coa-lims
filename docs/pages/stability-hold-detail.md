---
title: Hold record
urls: stability:hold_detail
views: stability.views.hold_detail
templates: ops/record.html
models: stability.Hold, core.ElectronicSignature
reviewed: 2026-11-10
---

## Purpose

One hold with its reason, who placed it and its release.

## Who can use it

- Sign-in required. Analyst, Reviewer, Quality, Admin and Auditor roles can open it; users without one of these roles receive 403.
- Action buttons are shown only to roles that can use them; the server checks again.

## Layout

- **Header**: breadcrumbs, title, identifier and status label, action buttons.
- **Details**: the facts below.

- **Signatures**: signer, meaning, server time, record and bound revision, content hash prefix; "No signatures yet."
- **History**: audit events in order with changes, reasons and actors; "No history recorded."

## Actions

| Action | Shown when | Who | Result |
|---|---|---|---|
| **Release hold** | Active; you did not place it | Quality | Opens the signing page |

## Fields

| Field | Model field | Type / units | Required | Meaning and use |
|---|---|---|---|---|
| Lot / Reserve sample | `Hold.lot`, `Hold.reserve` | Links | — | What is held |
| Kind / Reference / Reason | `Hold.kind`, `.reference`, `.reason` | Text | — | Basis |
| Placed by / Placed / Released | `Hold.placed_by`, `.placed_at`, `.released_at` | User, times | — | Lifecycle |

## Rules and hidden logic

- An active hold shows a warning notice that disposition and disposal are blocked.

## Related pages

- [Holds](/stability/holds/)
