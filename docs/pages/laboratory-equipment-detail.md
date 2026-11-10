---
title: Equipment record
urls: laboratory:equipment_detail
views: laboratory.views.equipment_detail
templates: ops/record.html
models: laboratory.Equipment, laboratory.Calibration, laboratory.Qualification, laboratory.ResourceUse, core.ElectronicSignature
reviewed: 2026-11-10
---

## Purpose

One instrument's fitness evidence: calibrations, qualification, service state and recorded uses.

## Who can use it

- Sign-in required. Analyst, Reviewer, Quality, Admin and Auditor roles can open it; users without one of these roles receive 403.
- Action buttons are shown only to roles that can use them; the server checks again.

## Layout

- **Header**: breadcrumbs, title, identifier and status label, action buttons.
- **Details**: the facts below.
- **Calibrations**: performed, due (inclusive), outcome, state, standard, certificate, recorded by, and **Accept** where you may accept.
- **Qualification evidence**: stage or use, state, validity, evidence reference.
- **Uses to assess after failure** (only while out of service): uses since the last accepted passing calibration before the failure.
- **Recent uses**: the latest 25.
- **Signatures**: signer, meaning, server time, record and bound revision, content hash prefix; "No signatures yet."
- **History**: audit events in order with changes, reasons and actors; "No history recorded."

## Actions

| Action | Shown when | Who | Result |
|---|---|---|---|
| **Record calibration** | Recorder role | Analyst, Quality | Opens the calibration form |
| **Record qualification** | Scientific role | Analyst, Reviewer, Quality | Opens the equipment qualification form |
| **Take out of service** | In service | Analyst, Reviewer, Quality | Opens the reason form |
| **Return to service** | Out of service | Quality | Opens the signed return-to-service page |
| **Accept** (in the table) | Calibration awaiting acceptance, not recorded by you | Reviewer | Opens the acceptance signing page |

## Fields

| Field | Model field | Type / units | Required | Meaning and use |
|---|---|---|---|---|
| Fitness label | — | Label | — | As on the list |
| Category, Location | `Equipment.category`, `.location` | Text | — | Identity |
| Qualification required | `Equipment.requires_qualification` | Yes/No | — | Whether qualification evidence is part of fitness |
| Service state / Last status change / Changed by | `Equipment.state`, `.status_changed_at`, `.status_changed_by` | Label, time, user | — | Who last put it out of or into service |
| Revision | `Equipment.revision` | Integer | — | Rises on every state change |

## Rules and hidden logic

- An out-of-service notice explains that return needs an independently accepted passing calibration and a signed impact assessment.
- Signatures and history include the equipment's calibrations and qualifications.

## Related pages

- [Equipment](/laboratory/equipment/)
- [Calibrations](/laboratory/calibrations/)
- [Qualifications](/laboratory/qualifications/)
