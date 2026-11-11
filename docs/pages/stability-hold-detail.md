---
title: Hold record
urls: stability:hold_detail
views: stability.views.hold_detail
templates: ops/record.html
models: stability.Hold, core.ElectronicSignature
reviewed: 2026-11-10
---

## Purpose

One hold on a lot (optionally one reserve sample) with its reason, who placed it, its state and its release time.

## Who can use it

- Sign-in required. Analyst, Reviewer, Quality, Admin and Auditor roles can open it; users without one of these roles receive 403.
- Action buttons are shown only to roles that can use them; the server checks again.
- Admin is read-only here: an account holding only the Admin role can read this page but sees no action buttons, and the server refuses every action (403). Admin plus a laboratory role keeps that role's actions; independence rules (no self-review) apply to everyone.

## Layout

- **Header**: breadcrumbs, title "<Kind> hold · <lot number>", identifier (HOLD-n) and state label (Active or Released), action buttons.
- **Notice**: while active, a warning "On hold: QC disposition and disposal of this lot are blocked." For an already released lot the hold does not alter the released record or issued certificate; it blocks future issue or amendment and disposal.
- **Details**: Lot (links to the lot record), Reserve sample (links to its record, blank if none), Kind, Reference, Reason, Placed by, Placed, Released, Revision.

- **Signatures**: signer, meaning, server time, record and bound revision, content hash prefix; "No signatures yet."
- **History**: audit events in order with changes, reasons and actors; "No history recorded."

## Actions

| Action | Shown when | Who | Result |
|---|---|---|---|
| **Release hold** | Hold is active and you did not place it, and you have the Quality role | Quality | Opens the signing page. Other users see no button; the signing page itself refuses non-Quality users (403) |

## Fields

| Field | Model field | Type / units | Required | Meaning and use |
|---|---|---|---|---|
| Lot / Reserve sample | `Hold.lot`, `Hold.reserve` | Links | — | What is held; a hold with no reserve covers the whole lot |
| Kind / Reference / Reason | `Hold.kind`, `.reference`, `.reason` | Investigation, Regulatory, Legal or Quality; text | — | Basis |
| Placed by / Placed / Released | `Hold.placed_by`, `.placed_at`, `.released_at` | User, times | — | Lifecycle; Released is blank while active |
| Revision | `Hold.revision` | Integer | — | Rises when the hold is released |

## Rules and hidden logic

- An active hold shows the warning notice. Any active hold on the lot, including one limited to a reserve sample, refuses QC disposition of that lot.
- A released hold is immutable. Signatures show the release signature; History shows `hold.placed` and `signed.approved` events.

## Related pages

- [Holds](/stability/holds/)
- Lot record and Reserve sample record (linked from Details)
