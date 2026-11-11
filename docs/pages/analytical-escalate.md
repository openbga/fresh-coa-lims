---
title: Escalate investigation
urls: analytical:escalate
views: analytical.views.escalate
templates: analytical/form.html, analytical/_summary.html
models: analytical.Investigation, analytical.InvestigationEntry
reviewed: 2026-11-10
---

## Purpose

Move a Phase I laboratory investigation to a Phase II full investigation.

## Who can use it

- Sign-in required. **Reviewers** or **quality**; others receive 403.
- No signature and no independence check.
- **Admin** alone, or a superuser without a lab role, receives 403 when opening the page or posting it; admin is not a scientific role. Admin together with the required role may act, subject to the same independence rules.

## Layout

- Heading "Escalate INV-n". Summary: Investigation, Lot, Trigger, Record revision.
- Form: **Reason**, hidden revision, **Cancel**, **Escalate investigation**.

## Actions

| Action | Shown when | Who | Result |
|---|---|---|---|
| **Escalate investigation** | Always | Reviewer, quality | "INV-n escalated to a full investigation."; returns to the investigation |
| **Cancel** | Always | Same | Returns to the investigation |

## Fields

| Field | Model field | Type / units | Required | Meaning and use |
|---|---|---|---|---|
| Reason | `InvestigationEntry.text`, `AuditEvent.reason` | Text, max 2000 | Yes | Stored as an Escalation entry |
| Expected revision (hidden) | `Investigation.revision` | Integer | Yes | Revision when the page opened |

## Rules and hidden logic

- **Wrong state**: opening or submitting this page when the record is not in the right state redirects to the investigation with the warning "Only a Phase I investigation can be escalated.".
- **Preconditions**: Phase I only; stale page "Record changed. Reload and review before continuing."
- **Effect**: phase becomes Phase II full investigation, an Escalation entry is added, the revision rises by 1, `investigation.escalated` is audited with the phases before and after.
- The lot stays held in both phases. The **Escalate investigation** link is shown only in Phase I.
- Not enforced by this page: a laboratory assessment is not required before escalating.

## Related pages

- Investigation record (return target).
