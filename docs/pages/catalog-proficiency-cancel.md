---
title: Cancel participation
urls: catalog:proficiency_cancel
views: catalog.proficiency_views.proficiency_cancel
templates: catalog/form.html
models: catalog.ProficiencyParticipation
reviewed: 2026-11-19
summary: Cancel a participation that will not take place, while it holds no result, with a reason. It stays in the list and no longer changes. Quality only.
---

## Common tasks

### Cancel a round

1. Check the participation shown on the page.
2. Explain why in [[Reason]] and select [[Cancel participation]]. The participation opens as cancelled.

### Keep it

1. Select [[Cancel]].

## Good to know

- Cancelling cannot be undone: a cancelled participation never changes again.
- Once a result is recorded you cannot cancel. Review the participation instead; a round the provider did not evaluate is recorded as not evaluated.
- The reason stays in the participation's history.
- A cancelled participation leaves the Reminders page.

## Purpose

Closes off a round the laboratory will not take part in, keeping the record and the reason.

## Who can use it

- Sign-in required. **quality** role only; others receive 403.
- A participation that is not open redirects to its record with a message such as "PT-n is closed: it no longer changes." One that holds a result redirects with "Results are recorded: review the participation instead. A round the provider did not evaluate is recorded as not evaluated."

## Layout

- **Header**: "Cancel participation · PT-n" with the introduction "For a round that will not take place or that the laboratory will not take part in. The participation stays in the list with your reason and no longer changes."
- **Record panel**: Participation, Method.
- **Form**: Reason; buttons **Cancel** and **Cancel participation**.

## Actions

| Action | Shown when | Who | Result |
|---|---|---|---|
| **Cancel participation** | Open, no result | Quality | Cancels; message "PT-n cancelled."; opens the participation |
| **Cancel** | Always | Quality | Returns to the participation without cancelling |

## Fields

| Field | Model field | Type / units | Required | Meaning and use |
|---|---|---|---|---|
| Reason | audit reason | Text, max 2000 | Yes | Why the round is cancelled |
| Expected revision (hidden) | `ProficiencyParticipation.revision` | Integer | Yes | Revision shown when the page opened |

## Rules and hidden logic

- **Stale record**: "Record changed. Reload before saving."
- **Checks under the lock**: still open, and still no result ("Results are recorded: review the participation instead. A round the provider did not evaluate is recorded as not evaluated.").
- **Effect**: state Cancelled with the time, revision raised by 1, audit event `participation.cancelled` with before and after values and your reason.
- **Database guards**: a cancelled participation can no longer be changed or deleted.
- Not enforced by this page: whether leaving a round is acceptable for the laboratory's scheme.

## Related pages

- Participation record
- [Proficiency testing](/catalog/proficiency/)
