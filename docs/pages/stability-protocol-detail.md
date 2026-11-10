---
title: Protocol record
urls: stability:protocol_detail
views: stability.views.protocol_detail
templates: ops/record.html
models: stability.Protocol, stability.ProtocolCondition, stability.ProtocolTimepoint, core.ElectronicSignature
reviewed: 2026-11-10
---

## Purpose

One protocol version with its storage conditions and timepoints.

## Who can use it

- Sign-in required. Analyst, Reviewer, Quality, Admin and Auditor roles can open it; users without one of these roles receive 403.
- Action buttons are shown only to roles that can use them; the server checks again.

## Layout

- **Header**: breadcrumbs, title, identifier and status label, action buttons.
- **Details**: the facts below.
- **Storage conditions**: condition, setpoint, temperature (°C), humidity (%).
- **Timepoints**: condition, timepoint, day, window (± days), tests.
- **Signatures**: signer, meaning, server time, record and bound revision, content hash prefix; "No signatures yet."
- **History**: audit events in order with changes, reasons and actors; "No history recorded."

## Actions

| Action | Shown when | Who | Result |
|---|---|---|---|
| **Approve** | Draft with at least one timepoint; you are not the author | Quality | Opens the signing page |
| **Add condition** / **Add timepoint** | Draft; you are the author (timepoint also needs a condition) | Analyst, Quality | Opens the add form |
| **Start study** | Approved | Analyst, Quality | Opens the new study form with this protocol selected |

## Fields

| Field | Model field | Type / units | Required | Meaning and use |
|---|---|---|---|---|
| Product, Protocol document, Test profile revision, Basis | `Protocol.*` | Text | — | Header |
| Author / Approved | `Protocol.author`, `.approved_at` | User, time | — | Authorship and approval time |
| Content digest | `Protocol.content_digest` | First 12 hex characters | — | Fingerprint of all conditions and timepoints, bound by the approval signature |
| Revision | `Protocol.revision` | Integer | — | Rises with every addition and the approval |

## Rules and hidden logic

- Once approved the content is frozen in the database; change it by creating a new version.

## Related pages

- [Stability protocols](/stability/protocols/)
- [Stability studies](/stability/studies/)
