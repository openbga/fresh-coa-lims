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

- **Header**: breadcrumbs, title, identifier and status label, action buttons.
- **Details**: the facts below.

- **Signatures**: signer, meaning, server time, record and bound revision, content hash prefix; "No signatures yet."
- **History**: audit events in order with changes, reasons and actors; "No history recorded."

## Actions

| Action | Shown when | Who | Result |
|---|---|---|---|
| **Approve** | Awaiting approval; you are neither the recorder nor the subject | Quality | Opens the signing page |
| **Revoke** | Approved; you are not the subject | Quality | Opens the signing page |

## Fields

| Field | Model field | Type / units | Required | Meaning and use |
|---|---|---|---|---|
| Subject / Type | `Qualification.user`, `.equipment` | Text | — | Exactly one subject |
| Valid from / Valid until | `Qualification.valid_from`, `.valid_until` | Dates (inclusive) | — | Validity window |
| Evidence reference / link / Scope | `Qualification.evidence_ref`, `.evidence_url`, `.scope_note` | Text | — | Controlled evidence |
| Recorded by / Revision | `Qualification.recorded_by`, `.revision` | User, integer | — | Authorship and revision |

## Rules and hidden logic

- The identifier is QUAL- plus the record number. Status Expired is shown after the last valid day.

## Related pages

- [Qualifications](/laboratory/qualifications/)
