---
title: Record decision
urls: impact:decide
views: impact.views.record_decide
templates: catalog/form.html
models: impact.Item, impact.Assessment, core.AuditEvent
reviewed: 2026-11-17
summary: Decide whether one record was affected, why, and what is done about it. A decision can be changed while the assessment is open. Quality only.
---

## Common tasks

### Mark a record not affected

1. On the assessment, select [[Record decision]] in the record's row.
2. Choose [[Decision]] Not affected, give [[Reason for the decision]] and select the button.

### Mark a record affected

1. Choose Affected, give the reason, and say in [[Follow-up]] what is done about it.
2. Enter the investigation, hold, certificate or quality record in [[Follow-up reference]] if there is one.

### Change an earlier decision

1. Select [[Change decision]] in the row. The earlier entries are filled in.

## Good to know

- Affected needs a follow-up: a retest under an investigation, a hold, a reassessment, a certificate withdrawn or amended, or a quality record.
- Recording Affected does not act on the record. A certificate, lot or test is dealt with on its own page.
- A change keeps every earlier decision in the audit trail.
- You cannot conclude an assessment in which you decided a record.

## Purpose

Quality's decision on one record the assessment names: affected or not, the reason, and the follow-up.

## Who can use it

- Sign-in required. **quality** role only; others receive 403.
- An assessment that is no longer open redirects to its record with "This impact assessment is no longer open."

## Layout

- Breadcrumbs (Impact assessments, IA-n, Record decision or Change decision), the introduction, the facts Assessment, the kind of record (Test, Lot, Stability study or Certificate) with its label, Now (its current status) and Why it is in the assessment, then the form, **Cancel** and the submit button.

## Actions

| Action | Shown when | Who | Result |
|---|---|---|---|
| **Record decision** / **Change decision** (submit) | Always (the title and button say Change when a decision exists) | Quality | Saves; message "Decision recorded for <record>."; returns to the assessment |
| **Cancel** | Always | Quality | Returns without saving |

## Fields

| Field | Model field | Type / units | Required | Meaning and use |
|---|---|---|---|---|
| Decision | `Item.decision` | Affected or Not affected | Yes | Whether the record may not be relied on as it stands |
| Reason for the decision | `Item.rationale`, audit reason | Text, max 4000 | Yes | Why |
| Follow-up | `Item.follow_up` | Text, max 4000 | When affected | What is done about it |
| Follow-up reference | `Item.follow_up_reference` | Text, max 200 | No | The investigation, hold, certificate or quality-system record |
| Expected revision (hidden) | `Item.revision` | Integer | Yes | The record's revision when the page opened |

## Rules and hidden logic

- **Messages**: "Choose whether the record was affected."; "Give the reason for the decision."; "Say what is done about it." when Affected has no follow-up.
- **Stale page**: "The record changed since you opened it. Reload and review." The record is locked and its revision checked.
- **Effect**: the decision, reason, follow-up, you and the time are stored; the record's revision and the assessment's revision rise; the audit event `impact.record_decided` keeps the values before and after.
- **Independence**: whoever decides a record cannot conclude the assessment.
- Not enforced by this page: that the follow-up is carried out. Not affected is accepted for a lot that has an active hold.
- The assessment changes none of the records it names.

## Related pages

- Impact assessment record
- Place hold
