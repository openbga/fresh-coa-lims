---
title: End data connection
urls: laboratory:equipment_connection_end
views: laboratory.views.equipment_connection_end
templates: ops/form.html
models: laboratory.Equipment, laboratory.DeviceConnection, core.AuditEvent
reviewed: 2026-11-18
summary: End the data connection of a balance or meter. No further reading is taken or recorded through it; values from the instrument are then typed. Quality only.
---

## Common tasks
### End the connection
1. In [[Reason]], say why readings are no longer taken through this connection.
2. Select [[End data connection]]. The equipment record opens with no current connection.
### Keep the connection
1. Select [[Cancel]] to return to the equipment record. Nothing changes.
## Good to know
- Readings already taken stay with their tests, with the connection they were taken through.
- A reading taken through this connection but not yet recorded in a replicate can no longer be recorded. Read again after setting a new connection.
- To change settings, use Set data connection instead: it ends this connection and records the new one together.

## Purpose

Stop taking readings from an instrument through its current data connection, for example when it moves to another computer or its interface is no longer verified.

## Who can use it

- Sign-in required. **Quality** only; others receive 403 when opening or posting the page.
- An account holding only the Admin role is refused (403). Admin plus Quality has Quality's authority.
- Equipment without a current connection redirects to its record with "This equipment has no data connection."

## Layout

- Breadcrumbs (Laboratory, Equipment, the asset, End data connection), title "End the data connection of ASSET".
- Introduction: the current connection's format, serial settings and recording date, then "No further reading is taken or recorded through it; readings taken already stay with their tests."
- The form in one panel and a **Cancel** / **End data connection** row.

## Actions

| Action | Shown when | Who | Result |
|---|---|---|---|
| **End data connection** | A connection is current (the equipment record offers it under More to Quality) | Quality | Ends it and opens the equipment record with "Data connection ended."; refusals appear on the form and your entry is kept (status 422) |
| **Cancel** | Always | Any | Returns to the equipment record without saving |

## Fields

| Field | Model field | Type / units | Required | Meaning and use |
|---|---|---|---|---|
| Reason | `AuditEvent.reason` | Text, max 2000 | Yes | Why the connection ends |
| Connection shown | — (hidden `connection`) | Id | — | The connection that was current when the page opened; only that one is ended |

## Rules and hidden logic

- Messages: "State why the data connection ends."; "The data connection of this equipment changed while you were editing. Reload the page and check the current connection." (the connection shown when the page opened is no longer current).
- In one transaction the equipment row is locked, the connection's end (who and when) is stored, its revision rises by 1 and `equipment.connection_ended` is audited on the equipment.
- The database allows a connection to be ended once and never deleted.

## Related pages

- Equipment record (return target).
- Set data connection.
