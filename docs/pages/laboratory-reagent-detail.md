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
- Admin is read-only here: an account holding only the Admin role can read this page but sees no action buttons, and the server refuses every action (403). Admin plus a laboratory role keeps that role's actions; independence rules (no self-review) apply to everyone.

## Layout

- **Header**: breadcrumbs, title (the name), identifier and state label (Rejected, Awaiting release, Expired, Expiring soon or Released), action buttons. A rejected lot also shows a red notice: "This lot cannot be used; prepared solutions from it are also blocked."
- **Details**: the facts below.
- **Preparations from this lot**: identifier (link), name, state for every solution that names this lot as its source. Empty: "No prepared solutions record this lot as their source."
- **Uses**: the latest 25 (used, work, activity, by; the Work label is the sample reference for sample work, otherwise the raw context as recorded). Empty: "No use recorded."
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
| Kind, Supplier, Supplier lot | `ReagentLot.kind`, `.supplier`, `.lot_number` | Text | — | Identity |
| Received or prepared / Expiry (last day of use) | `ReagentLot.received_on`, `.expiry_date` | Dates, inclusive | — | Provenance and last day of use |
| Assigned purity | `ReagentLot.assigned_purity`, `.purity_unit` | Decimal with unit, trailing zeros trimmed | — | Certified or assigned value; blank when none |
| Source lot | `ReagentLot.parent` | Link | — | For prepared solutions |
| Preparation | `ReagentLot.preparation_note` | Text | — | Diluent, amounts and calculation |
| Certificate | `ReagentLot.certificate_ref`, `.certificate_url` | Link (reference as label) or text | — | External evidence; untrusted link |
| Recorded by | `ReagentLot.recorded_by` | User | — | Who recorded the lot |
| Released | `ReagentLot.released_at` | Time with zone | — | Signature time of release; blank until released |
| Revision | `ReagentLot.revision` | Integer | — | Rises on release and rejection |

## Rules and hidden logic

- **Buttons**: Release for use shows to Reviewers other than the recorder on lots awaiting release; Reject lot shows to Analyst, Reviewer and Quality on any lot not yet rejected, including released ones. The server re-checks on open and save.
- Signatures and history are those of this lot only. An unknown ID returns 404.

## Related pages

- Release and reject pages (use the action buttons); source lot and preparations link to their own records
- [Resource use](/laboratory/uses/)
- [Reagents and standards](/laboratory/reagents/)
