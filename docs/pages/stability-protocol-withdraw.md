---
title: Withdraw draft protocol
urls: stability:protocol_withdraw
views: stability.views.protocol_withdraw
templates: ops/form.html
models: stability.Protocol, core.AuditEvent
reviewed: 2026-11-15
---

## Purpose

Withdraw a draft stability protocol that will not be approved, so that the next version of its code can be drafted. For example a draft whose specification cannot state one of its tests, or that names the wrong specification.

## Who can use it

- Sign-in required. Roles: Analyst or Quality; others receive 403.
- Only the draft's author or a Quality user may withdraw it; anyone else receives 403 ("Only the draft's author or a quality person withdraws it.").
- An account holding only the Admin role is refused (403) when it opens or submits this page.

## Layout

- Breadcrumbs (Protocols, protocol, Withdraw draft), title "Withdraw <code> v<n>", an introduction (a withdrawn draft is never approved and keeps its content; the next version of the code can then be drafted), the form, and a **Cancel** / **Withdraw draft** row.

## Actions

| Action | Shown when | Who | Result |
|---|---|---|---|
| **Withdraw draft** | Always on this page | The draft's author (Analyst or Quality) or a Quality user | Withdraws the draft, shows "<code> v<n> withdrawn. The next version of <code> can be drafted." and returns to the protocol; refusals appear as an error summary and your entry is kept (status 422) |
| **Cancel** | Always | Any | Returns to the protocol without saving |

## Fields

| Field | Model field | Type / units | Required | Meaning and use |
|---|---|---|---|---|
| Reason | `AuditEvent.reason` | Text, max 2000 | Yes | Why the draft is withdrawn |
| (hidden) Expected revision | `Protocol.revision` | Integer | Yes | The revision you saw; a draft changed since is refused ("Record changed. Reload before withdrawing.") |

## Rules and hidden logic

- Only a Draft can be withdrawn; opening the page for another state returns to the protocol with "Only a draft protocol can be withdrawn."
- The withdrawal is not signed. It changes only the state (to Withdrawn) and the record revision; the database refuses any other change, and a withdrawn protocol takes no more conditions or timepoints. Event `protocol.withdrawn` with your reason.
- A withdrawn protocol is never approved and starts no study. A new version of the same code can then be created; it gets the next version number.

## Related pages

- Protocol record (return target)
- Protocols list
- New protocol (to draft the next version)
