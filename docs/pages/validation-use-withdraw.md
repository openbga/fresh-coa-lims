---
title: Withdraw intended use
urls: validation:use_withdraw
views: validation.views.use_withdraw
templates: ops/form.html
models: validation.UseAcceptance, core.AuditEvent
reviewed: 2026-11-17
summary: Withdraw a record of the intended use that will not be accepted. It keeps its content and is never accepted; record a new one to correct it.
---

## Common tasks
### Withdraw the record
1. Give the [[Reason for withdrawing]].
2. Select [[Withdraw]]. You return to the record, which shows as Withdrawn.
### Correct the intended use
1. After withdrawing, go to the list through [[Validation]] and select [[New intended use]] to record a corrected one.
### Leave without withdrawing
1. Select [[Cancel]] to return to the record. Nothing changes.
## Good to know
- Only a record awaiting acceptance can be withdrawn. An accepted record is replaced only when a newer record is accepted, which supersedes it.
- Any quality person can withdraw it, including the person who recorded it.
- The withdrawal is not signed, but the record's history keeps it with your reason.
- If the record changed after you opened the page, the withdrawal is refused. Reload first.

## Purpose

Withdraw a record of the intended use that will not be accepted, for example because it names the wrong assays. A new record is then made to correct it.

## Who can use it

- Sign-in required. Role: Quality. Others, including an account holding only the Admin role, receive 403.
- Any Quality user may withdraw it, including its recorder.

## Layout

- Breadcrumbs (Validation, UA-n, Withdraw), title "Withdraw UA-n", an introduction ("A withdrawn record of the intended use is never accepted and keeps its content in the record. Record a new record of the intended use to correct it."), the form, **Cancel** and **Withdraw**.

## Actions

| Action | Shown when | Who | Result |
|---|---|---|---|
| **Withdraw** | Always on this page | Quality | Withdraws the record; shows "UA-n withdrawn." and returns to the record. Refusals appear as an error with your entry kept (status 422) |
| **Cancel** | Always | Quality | Returns to the record without saving |

## Fields

| Field | Model field | Type / units | Required | Meaning and use |
|---|---|---|---|---|
| Reason for withdrawing | `AuditEvent.reason` | Text, max 2000 | Yes | Why it is withdrawn |
| (hidden) Expected revision | `UseAcceptance.revision` | Integer | Yes | The revision you saw; a changed record is refused: "Record changed. Reload before withdrawing." |

## Rules and hidden logic

- Only a record awaiting acceptance can be withdrawn. Opening the page for another state returns to the record with "This record is <state>; only a record awaiting acceptance can be accepted or withdrawn."
- The withdrawal is not signed. It sets the state to Withdrawn with the time and raises the revision; the database refuses any other change. Audit event `use_acceptance.withdrawn` with your reason.
- An accepted record cannot be withdrawn; it is replaced only by accepting a newer record, which supersedes it.

## Related pages

- Intended use record (return target)
- [Intended use](/validation/)
- Record intended use (to record a corrected one)
