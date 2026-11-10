---
title: Record calibration
urls: laboratory:calibration_new
views: laboratory.views.calibration_new
templates: ops/form.html
models: laboratory.Calibration, laboratory.Equipment, core.AuditEvent
reviewed: 2026-11-10
---

## Purpose

Record a calibration or verification event for one instrument.

## Who can use it

- Sign-in required. Roles: Analyst or Quality; everyone else (including Reviewer) receives 403. The equipment must exist (404 otherwise).

## Layout

- Breadcrumbs (Laboratory, Equipment, the asset, Record calibration), title "Record calibration · ASSET", the introduction "A failed calibration removes the equipment from service immediately.", the form in one panel, and a **Cancel** / submit row.

## Actions

| Action | Shown when | Who | Result |
|---|---|---|---|
| **Record calibration** | Always | Analyst or Quality; everyone else receives 403 | Saves and opens the equipment record with "Calibration recorded; independent acceptance needed." (Pass) or the warning "Failed calibration recorded; equipment is out of service pending impact assessment." (Fail); field and domain errors appear above the form, your entries are kept (status 422) |
| **Cancel** | Always | Any | Returns without saving |

## Fields

| Field | Model field | Type / units | Required | Meaning and use |
|---|---|---|---|---|
| Performed at | `Calibration.performed_at` | Date and time (deployment time zone, UTC by default) | Yes | When the calibration was done; not in the future |
| Due date | `Calibration.due_date` | Date | Yes | Last day the calibration stays valid (inclusive) |
| Outcome | `Calibration.outcome` | Pass / Fail | Yes | A failure takes the equipment out of service at once |
| Standard ref | `Calibration.standard_ref` | Text, max 200 | Yes | Reference standard or certificate giving traceability |
| Certificate ref / Certificate url | `Calibration.certificate_ref`, `.certificate_url` | Text, max 200; http(s) link, max 500 | No | Controlled external evidence; the link is untrusted text |
| Tolerance note | `Calibration.tolerance_note` | Multi-line text | No | As-found/as-left values and limits |
| Reason | `AuditEvent.reason` | Text, max 2000 | Yes | Recorded with the event |

## Rules and hidden logic

- Messages: "A calibration cannot be performed in the future."; "The due date cannot precede the calibration date."
- A passing record counts for fitness only after a different reviewer signs its acceptance. A failed record counts immediately and, if the equipment was in service, sets it Out of service in the same transaction (events `calibration.recorded` and `equipment.out_of_service`). The success message says so.
- A failure on equipment that is already out of service records the calibration only; the service state is unchanged.
- Calibration records cannot be edited or deleted; record a new one.

## Related pages

- Equipment record
- [Calibrations](/laboratory/calibrations/)
