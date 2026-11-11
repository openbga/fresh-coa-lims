---
title: Qualification record
urls: laboratory:qualification_detail
views: laboratory.views.qualification_detail
templates: ops/record.html
models: laboratory.Qualification, core.ElectronicSignature
reviewed: 2026-11-10
---

## Purpose

Evidence that a person or instrument is qualified for an activity within stated dates.

## Who can use it

- Sign-in required. Analyst, Reviewer, Quality, Admin and Auditor roles can open it; users without one of these roles receive 403.
- Action buttons are shown only to roles that can use them; the server checks again.

## Layout

- **Header**: breadcrumbs, title (the activity), the identifier QUAL-n and the state label (Awaiting approval, Approved, "Approved, starts <date>" before its valid-from date, Expired or Revoked), action buttons.
- **Details**: the facts below.
- **Signatures**: signer, meaning, server time, record and bound revision, content hash prefix; "No signatures yet."
- **History**: audit events in order with changes, reasons and actors; "No history recorded."

## Actions

| Action | Shown when | Who | Result |
|---|---|---|---|
| **Approve** | Awaiting approval; you are neither the recorder nor the subject | Quality | Opens the approval signing page |
| **Revoke** | Approved (including past its last day); you are not the subject | Quality | Opens the revocation signing page |
| Evidence link | An evidence URL was recorded | Any reader | Opens the external link (`noopener noreferrer`); treat its content as untrusted |

## Fields

| Field | Model field | Type / units | Required | Meaning and use |
|---|---|---|---|---|
| Subject / Type | `Qualification.user`, `.equipment` | Username or asset ID; Analyst or Equipment | — | Exactly one subject |
| Valid from / Valid until | `Qualification.valid_from`, `.valid_until` | Dates (inclusive) | — | Validity window |
| Evidence reference / Evidence link / Scope | `Qualification.evidence_ref`, `.evidence_url`, `.scope_note` | Text; http(s) link; text | — | Controlled evidence and its limits; blank when not given |
| Recorded by / Revision | `Qualification.recorded_by`, `.revision` | User, integer | — | Authorship and revision |

## Rules and hidden logic

- The identifier is QUAL- plus the record number. State Expired is shown for an approved record after its last valid day.
- Signatures and history are those of this record only. An unknown ID returns 404.
- The record is immutable apart from its state changes (database guard); there is no edit.

## Related pages

- [Qualifications](/laboratory/qualifications/)
