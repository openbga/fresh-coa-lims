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

- **Header**: breadcrumbs, title, identifier and status label, action buttons.
- **Details**: the facts below.
- **Retention obligations**: anchor, anchor date, months, retain-through date, basis, status (Cleared or Retained) and **Set anchor**.
- **Holds** on this reserve sample.
- **Disposal readiness**: every current blocking reason, or a note that nothing blocks. No disposal action exists in this system.
- **Signatures**: signer, meaning, server time, record and bound revision, content hash prefix; "No signatures yet."
- **History**: audit events in order with changes, reasons and actors; "No history recorded."

## Actions

| Action | Shown when | Who | Result |
|---|---|---|---|
| **Record retention obligation** | Authoring role | Analyst, Quality | Opens the obligation form for this reserve |
| **Place hold** | Scientific role | Analyst, Reviewer, Quality | Opens the hold form |
| **Set anchor** (in the table) | Anchor unknown | Analyst, Quality | Opens the anchor form |

## Fields

| Field | Model field | Type / units | Required | Meaning and use |
|---|---|---|---|---|
| Lot, Container, Location | `ReserveSample.*` | Text, link | — | Identity |
| Quantity retained / One test set / Multiple | `ReserveSample.quantity`, `.test_quantity` | Decimal with unit | — | Quantity check against the minimum |

## Rules and hidden logic

- Retention is the anchor date plus the stated months, per obligation; all obligations and holds must clear. No obligation recorded means applicability is unresolved and blocks disposal.

## Related pages

- [Reserve samples](/stability/reserves/)
- [Holds](/stability/holds/)
