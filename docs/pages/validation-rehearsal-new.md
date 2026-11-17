---
title: Record rehearsal
urls: validation:rehearsal_new
views: validation.views.rehearsal_new
templates: catalog/form.html
models: validation.Rehearsal, core.AuditEvent
reviewed: 2026-11-17
---

## Purpose

Record a rehearsal that already took place: a recovery from backup, a period of downtime with reconciliation, or an upgrade. You then attach the evidence, and a Quality user who did not record it accepts the record.

## Who can use it

- Sign-in required. Roles: Quality or Admin. Others receive 403.
- The record is not signed. Its recorder cannot accept it.

## Layout

- Breadcrumbs (Validation, Rehearsals, Record rehearsal), an introduction, and the form in four groups: **Rehearsal**, **How it was performed**, **Result**, **Change control**; then **Cancel** and **Record rehearsal**.

## Actions

| Action | Shown when | Who | Result |
|---|---|---|---|
| **Record rehearsal** | Always | Quality, Admin | Creates the record awaiting acceptance; shows "RH-n recorded. Attach its evidence; a quality person accepts it." and opens it. Refusals appear as errors with entries kept (status 422) |
| **Cancel** | Always | Quality, Admin | Returns to the list |

## Fields

| Field | Model field | Type / units | Required | Meaning and use |
|---|---|---|---|---|
| Rehearsal of | `Rehearsal.kind` | Choice | Yes | Recovery from backup, Downtime and reconciliation, Upgrade |
| Title | `Rehearsal.title` | Text, max 160 | Yes | Short name |
| Performed on | `Rehearsal.performed_on` | Date | Yes | The day it was performed; not in the future |
| Release before | `Rehearsal.previous_release` | Text, max 80 | Only for an upgrade | The release or source revision upgraded from |
| Release | `Rehearsal.release` | Text, max 80 | Yes | Release rehearsed; for an upgrade, the one upgraded to. Starts filled with the running release when the deployment states one |
| Environment | `Rehearsal.environment` | Text, max 200 | Yes | Where it was performed |
| Procedure | `Rehearsal.procedure_ref` | Text, max 200 | Yes | Procedure followed, with its revision |
| Acceptance criteria | `Rehearsal.acceptance_criteria` | Text, max 4000 | Yes | What had to be shown |
| Outcome | `Rehearsal.outcome` | Radio | Yes | **Criteria met** or **Criteria not met** |
| Observations | `Rehearsal.observations` | Text, max 4000 | Yes | Steps, measured times, records reconciled, checks run |
| Issues and actions | `Rehearsal.issues_and_actions` | Text, max 4000 | Only when criteria were not met | Deviations and how each was or will be corrected |
| Reason | `AuditEvent.reason` | Text, max 2000 | Yes | Recorded in the audit trail |

## Rules and hidden logic

- Messages: "An upgrade names the release before it."; "State what was not met and the actions taken or planned."; "A rehearsal is recorded after it took place." (a date after today).
- The database refuses blank required text, an upgrade without a previous release and a not-met outcome without issues.
- Effect: one transaction creates the rehearsal in state **Awaiting acceptance** at revision 1 and writes the audit event `rehearsal.recorded` with your reason.
- Recorded content is never edited. To correct a record, withdraw it and record a new one.
- Nothing is held or blocked by a rehearsal, whatever its outcome.

## Related pages

- [Rehearsals](/validation/rehearsals/) (Cancel returns here)
- Rehearsal record (opened after saving)
