---
title: Protocol record
urls: stability:protocol_detail
views: stability.views.protocol_detail
templates: ops/record.html
models: stability.Protocol, stability.ProtocolCondition, stability.ProtocolTimepoint, core.ElectronicSignature
reviewed: 2026-11-10
---

## Purpose

One protocol version (code and version number) with its header facts, storage conditions and timepoints, and the actions that move it forward.

## Who can use it

- Sign-in required. Analyst, Reviewer, Quality, Admin and Auditor roles can open it; users without one of these roles receive 403.
- Action buttons are shown only to roles that can use them; the server checks again.
- Admin is read-only here: an account holding only the Admin role can read this page but sees no action buttons, and the server refuses every action (403). Admin plus a laboratory role keeps that role's actions; independence rules (no self-review) apply to everyone.

## Layout

- **Header**: breadcrumbs, title, identifier and status label, action buttons.
- **Details**: Product, Protocol document (a link when a URL is set, otherwise the reference text), Test profile revision, Basis, Author, Approved (time), Content digest, Revision.
- **Storage conditions**: condition, setpoint, temperature (°C), humidity (%).
- **Timepoints**: condition, timepoint, day, window (± days), tests (codes comma separated). Ordered by condition then day. Empty states: "No conditions yet. Add the approved storage conditions." and "No timepoints yet."
- **Signatures**: signer, meaning, server time, record and bound revision, content hash prefix; "No signatures yet."
- **History**: audit events in order with changes, reasons and actors; "No history recorded."

## Actions

| Action | Shown when | Who | Result |
|---|---|---|---|
| **Approve** | Draft with at least one timepoint, you have the Quality role and you are not the author | Quality | Opens the signing page, where the full approval preconditions are checked |
| **Add condition** / **Add timepoint** | Draft; you are the author and an Analyst or Quality user (timepoint also needs at least one condition) | Analyst, Quality (author only) | Opens the add form |
| **Start study** | State Approved (not Draft or Superseded) | Analyst, Quality | Opens the new study form with this protocol preselected |

## Fields

| Field | Model field | Type / units | Required | Meaning and use |
|---|---|---|---|---|
| Product, Protocol document, Test profile revision, Basis | `Protocol.product`, `.document_ref`, `.document_url`, `.test_profile_ref`, `.basis` | Text; document link | — | Header; the header is frozen after creation |
| Title / State | `Protocol.title`, `.state` | Text; Draft, Approved or Superseded | — | Page title and status label |
| Storage conditions | `ProtocolCondition.*` | Label, setpoint, temperature (°C), humidity (%) | — | Blank when not set |
| Timepoints | `ProtocolTimepoint.*` | Day (interval from time zero), window (± days), test codes | — | Pulls are scheduled from these |
| Author / Approved | `Protocol.author`, `.approved_at` | User, time | — | Authorship and approval time |
| Content digest | `Protocol.content_digest` | First 12 hex characters | — | Fingerprint of all conditions and timepoints, bound by the approval signature |
| Revision | `Protocol.revision` | Integer | — | Rises with every addition and the approval |

## Rules and hidden logic

- Once approved the content is frozen in the database; change it by creating a new version. Superseded versions stay readable.
- Add buttons are visible to the draft's author only, but the server also refuses anyone else.
- Signatures lists the approval signature; History lists `protocol.created`, additions and approval events.

## Related pages

- [Stability protocols](/stability/protocols/)
- [Stability studies](/stability/studies/)
- Add storage condition, Add timepoint and Approve protocol (opened from the actions above)
