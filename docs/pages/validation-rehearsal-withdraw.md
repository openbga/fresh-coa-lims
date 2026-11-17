---
title: Withdraw rehearsal
urls: validation:rehearsal_withdraw
views: validation.views.rehearsal_withdraw
templates: ops/form.html
models: validation.Rehearsal, core.AuditEvent
reviewed: 2026-11-17
---

## Purpose

Withdraw a rehearsal record that will not be accepted, for example one recorded with a wrong release. A new rehearsal is then recorded to correct it.

## Who can use it

- Sign-in required. Roles to open the page: Quality or Admin; others receive 403.
- Only the person who recorded the rehearsal or a Quality user may withdraw it. An Admin who did not record it and is not Quality receives 403 ("Only the person who recorded the rehearsal or a quality person withdraws it.").

## Layout

- Breadcrumbs (Validation, Rehearsals, RH-n, Withdraw), title "Withdraw RH-n", an introduction ("A withdrawn rehearsal is never accepted and keeps its content in the record. Record a new rehearsal to correct it."), the form, **Cancel** and **Withdraw**.

## Actions

| Action | Shown when | Who | Result |
|---|---|---|---|
| **Withdraw** | Always on this page | Recorder or Quality | Withdraws the rehearsal; shows "RH-n withdrawn." and returns to the rehearsal. Refusals appear as an error with your entry kept (status 422) |
| **Cancel** | Always | Recorder or Quality | Returns to the rehearsal without saving |

## Fields

| Field | Model field | Type / units | Required | Meaning and use |
|---|---|---|---|---|
| Reason for withdrawing | `AuditEvent.reason` | Text, max 2000 | Yes | Why it is withdrawn |
| (hidden) Expected revision | `Rehearsal.revision` | Integer | Yes | The revision you saw; a changed record is refused: "Record changed. Reload before withdrawing." |

## Rules and hidden logic

- Only a rehearsal awaiting acceptance can be withdrawn. Opening the page for another state returns to the rehearsal with "This rehearsal is <state>; only a rehearsal awaiting acceptance can be accepted or withdrawn."
- The withdrawal is not signed. It sets the state to Withdrawn with the time and raises the revision; the database refuses any other change. Audit event `rehearsal.withdrawn` with your reason.
- The evidence files stay stored and downloadable; a withdrawn rehearsal takes no more files. An accepted rehearsal cannot be withdrawn.

## Related pages

- Rehearsal record (return target)
- [Rehearsals](/validation/rehearsals/)
- Record rehearsal (to record a corrected one)
