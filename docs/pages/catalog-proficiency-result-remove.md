---
title: Remove result
urls: catalog:proficiency_result_remove
views: catalog.proficiency_views.proficiency_result_remove
templates: catalog/form.html
models: catalog.ProficiencyResult, catalog.ProficiencyParticipation
reviewed: 2026-11-19
summary: Remove a result from an open participation, with a reason. The removal stays in the participation's history.
---

## Common tasks

### Remove a result

1. Check the measurand, result, score and outcome shown on the page.
2. Explain why in [[Reason]] and select [[Remove result]]. The participation opens.

### Correct a result

1. Remove it here, then select [[Record result]] on the participation to add it again.

### Keep it

1. Select [[Cancel]].

## Good to know

- Only an open participation loses results; after review they are frozen.
- The removed result is kept in the history with your reason.
- Removing a result makes you an author of the data, so you cannot review this participation.
- If the participation changed after you opened this page, removal is refused. Reload and try again.

## Purpose

Removes a result from an open participation while keeping what was removed in the audit trail.

## Who can use it

- Sign-in required. **analyst**, **reviewer** or **quality** role; others receive 403.
- A participation that is not open redirects to its record with a message such as "PT-n is closed: it no longer changes." A participation under corrective follow-up gives "PT-n is reviewed: its plan, report and results no longer change; its corrective follow-up is open." A result of another participation gives 404.

## Layout

- **Header**: "Remove result · PT-n" with the introduction "Removal is recorded in the participation's history with your reason."
- **Record panel**: Measurand, Laboratory's result (with its unit), Score ("z = 1.2", similarly z′, ζ and En, or "No score"), Outcome.
- **Form**: Reason; buttons **Cancel** and **Remove result**.

## Actions

| Action | Shown when | Who | Result |
|---|---|---|---|
| **Remove result** | Open | Analyst, reviewer, quality | Deletes the result; message "<measurand> removed from PT-n."; opens the participation |
| **Cancel** | Always | Same | Returns to the participation |

## Fields

| Field | Model field | Type / units | Required | Meaning and use |
|---|---|---|---|---|
| Reason | audit reason | Text, max 2000 | Yes | Why it is removed |
| Expected revision (hidden) | participation `revision` | Integer | Yes | Revision shown when the page opened |

## Rules and hidden logic

- **Stale record**: "Record changed. Reload before saving."
- **Effect**: the participation's revision increases by 1; audit event `participation.result_removed` with the removed result and your reason.
- **Database guard**: results change only while their participation is open, and are never updated.
- Removing the last result means the participation is not ready for review again ("Record the laboratory's results with the provider's scores.").

## Related pages

- Participation record
- Record result
