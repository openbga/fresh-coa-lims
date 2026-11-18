---
title: Add record
urls: impact:add
views: impact.views.record_add
templates: catalog/form.html
models: impact.Assessment, impact.Item, core.AuditEvent
reviewed: 2026-11-17
summary: Add a test, lot, stability study or issued certificate that the problem may have affected and the cause does not find by itself, with the reason. Quality only.
---

## Common tasks

### Add a lot the system did not find

1. On the assessment, select [[Add record]].
2. Choose Lot in [[Kind of record]] and enter the lot number in [[Record]].
3. Say why in [[Why it may be affected]] and select [[Add record]].

### Add a test or a certificate

1. Choose Test and enter T-n (or the number), or choose Certificate and enter its number.

## Good to know

- Adding a lot also brings in the certificates issued for it, the next time records are found.
- A record can be named once. Adding it again is refused.
- A certificate must have been issued to be added.
- You cannot conclude an assessment in which you added a record yourself.

## Purpose

Names a record that quality judges may be affected but that the cause and its follow-through did not find, for example for the cause Other.

## Who can use it

- Sign-in required. **quality** role only; others receive 403.
- An assessment that is no longer open redirects to its record with "This impact assessment is no longer open."

## Layout

- Breadcrumbs (Impact assessments, IA-n, Add record), the introduction, the fact Assessment, the form, **Cancel** and **Add record**.

## Actions

| Action | Shown when | Who | Result |
|---|---|---|---|
| **Add record** | Always | Quality | Adds the record undecided; message "<record> added to IA-n."; returns to the record |
| **Cancel** | Always | Quality | Returns to the record |

## Fields

| Field | Model field | Type / units | Required | Meaning and use |
|---|---|---|---|---|
| Kind of record | `Item.kind` | Test, Lot, Stability study, Certificate | Yes | What the next field names |
| Record | `Item.test`, `lot`, `study`, `report` | Text, max 120 | Yes | A test number (T-12), a lot number, a stability study identifier or a certificate number (CoA-...) |
| Why it may be affected | `Item.basis`, audit reason | Text, max 2000 | Yes | Shown as the record's basis |
| Expected revision (hidden) | `Assessment.revision` | Integer | Yes | The revision shown when the page opened |

## Rules and hidden logic

- **Lookups**: a test is found by T-n or the digits; a lot by its number; a study by its identifier; a certificate by its number, only when it has an issued version. Otherwise "No test is called X.", "No lot is called X.", "No stability study is called X." or "No issued certificate is called X."
- **Messages**: "Name the record."; "Say why the record may be affected."; "This record is already in the assessment."; "An assessment covers at most 500 records; assess the rest in another assessment."
- **Stale page**: "The assessment changed since you opened it. Reload and review."
- **Effect**: the record is added with origin "Added by quality", no decision, and you as the person who added it; the audit event `impact.record_added` is written and the revision rises.
- **Independence**: whoever adds a record cannot conclude the assessment. A record found from the cause is not authored by anyone.
- The assessment changes none of the records it names.

## Related pages

- Impact assessment record
