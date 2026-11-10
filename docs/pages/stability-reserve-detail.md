---
title: Reserve sample record
urls: stability:reserve_detail
views: stability.views.reserve_detail
templates: ops/record.html
models: stability.ReserveSample, stability.RetentionObligation, stability.Hold, core.ElectronicSignature
reviewed: 2026-11-10
---

## Purpose

A reserve sample with its retention obligations, holds and what currently prevents disposal.

## Who can use it

- Sign-in required. Analyst, Reviewer, Quality, Admin and Auditor roles can open it; users without one of these roles receive 403.
- Action buttons are shown only to roles that can use them; the server checks again.

## Layout

- **Header**: breadcrumbs (Reserve samples, this reserve), title "Reserve of <lot number>", identifier, status label (Meets minimum or Below minimum) and action buttons.
- **Details**: the facts below.
- **Retention obligations**: anchor, anchor date, months, retain-through date, basis, status (Cleared or Retained) and a **Set anchor** link. Empty state: "No obligation recorded: applicability is unresolved, so nothing may be disposed of." A note says every obligation computes its own deadline and all must clear.
- **Holds** on this reserve sample: hold (links to the hold), kind, state, placed by. Empty state: "No holds on this reserve sample."
- **Disposal readiness**: every current blocking reason, or "Nothing currently blocks disposal. No disposal action exists in this system yet."
- **Signatures**: signer, meaning, server time, record and bound revision, content hash prefix; "No signatures yet."
- **History**: audit events in order with changes, reasons and actors; "No history recorded."

## Actions

| Action | Shown when | Who | Result |
|---|---|---|---|
| **Record retention obligation** | Analyst or Quality | Analyst, Quality | Opens the obligation form linked to this reserve |
| **Place hold** | Analyst, Reviewer or Quality | Analyst, Reviewer, Quality | Opens the hold form linked to this reserve |
| **Set anchor** (in the obligations table) | The obligation has no anchor date yet, and you are Analyst or Quality | Analyst, Quality | Opens the anchor form |

Other roles do not see these controls; the server refuses them with 403.

## Fields

| Field | Model field | Type / units | Required | Meaning and use |
|---|---|---|---|---|
| Lot | `ReserveSample.lot` | Link | — | Opens the lot |
| Container / Location | `ReserveSample.container_description`, `.storage_location` | Text | — | As retained |
| Quantity retained / One test set | `ReserveSample.quantity`, `.test_quantity`, `.quantity_unit` | Decimal with unit | — | Amounts recorded |
| Multiple of test set | computed | Quantity / test set, 2 places | — | Shown with the minimum multiple, for example "2.50 (minimum 2.00)" |
| Retained on / Recorded by | `ReserveSample.retained_on`, `.recorded_by` | Date, user | — | Who and when |
| Obligation columns | `RetentionObligation.anchor_kind`, `.anchor_date`, `.offset_months`, `.basis` | Choice, date, months, text | — | Retain through is anchor date plus months; blank while the anchor is unknown |

## Rules and hidden logic

- **Retention**: per obligation, the anchor date plus the stated months. An obligation is Retained while the anchor is unknown ("<anchor> is not yet known.") or today is on or before the retain-through date; otherwise Cleared.
- **Obligations shown**: the table lists only obligations linked to this reserve; disposal readiness also counts lot-level obligations (not tied to a reserve) of the same lot.
- **Holds**: the table lists holds placed on this reserve; readiness counts active holds on this reserve and active lot-wide holds on the same lot.
- **Disposal readiness**: lists a blocker for no obligation recorded, each Retained obligation, and each active hold. No disposal action exists.
- **Not editable**: the reserve record is immutable; this page has no signing or edit action.

## Related pages

- [Reserve samples](/stability/reserves/)
- [Holds](/stability/holds/)
- Lot record (from the Lot link)
- Record retention obligation, Set anchor, Place hold (forms opened from here)
