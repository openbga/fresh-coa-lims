---
title: Find affected records
urls: impact:find
views: impact.views.assessment_find
templates: catalog/form.html
models: impact.Assessment, impact.Item, core.AuditEvent
reviewed: 2026-11-17
summary: Add the records the cause finds now that are not in the assessment yet, for example a test recorded since it started. They are added without a decision. Quality only.
---

## Common tasks

### Add newly found records

1. On the assessment, select [[Find affected records]]. It shows when the cause finds records not yet in it.
2. Check the list, then select the button that adds them.

### Check why a record is proposed

1. Read the line for each record: it names the kind of record and why it is found.
2. Select [[Cancel]] if a record should not be added; none is added until you select the button.

## Good to know

- The records are added without a decision. Each still needs one before the assessment can be concluded.
- Only records found from the cause and the lots and certificates they lead to are added. A record already in the assessment is not proposed again.
- Finding is never refused for the number of records: a record the cause finds must be in the assessment before it is concluded.
- If the assessment changed since the page opened, reload and review.

## Purpose

Brings an open assessment up to date with the cause. Work recorded after the assessment started, or a certificate of a lot added to it, can be covered here.

## Who can use it

- Sign-in required. **quality** role only; others receive 403.
- An assessment that is no longer open redirects to its record with "This impact assessment is no longer open."

## Layout

- Breadcrumbs (Impact assessments, IA-n, Find affected records), the introduction, then facts: Assessment, and one line per record found (its kind and the basis, up to 50, then "N more"). Buttons: **Cancel** and the submit button.

## Actions

| Action | Shown when | Who | Result |
|---|---|---|---|
| **Add N record(s)** | Records are found | Quality | Adds them; message "N record(s) added to IA-n."; returns to the record |
| **Find again** | Nothing is found | Quality | Adds nothing; returns to the record with "The cause finds no record that is not in the assessment." |
| **Cancel** | Always | Quality | Returns to the record |

## Fields

| Field | Model field | Type / units | Required | Meaning and use |
|---|---|---|---|---|
| Expected revision (hidden) | `Assessment.revision` | Integer | Yes | The revision shown when the page opened |

## Rules and hidden logic

- Found records are those of the New impact assessment page's rules for the cause, then their follow-through to lots, studies and certificates, including those of records quality added.
- The assessment is locked, the revision is checked, and records are added under that lock. A stale page is refused with "The assessment changed since you opened it. Reload and review."
- Effect: the records are added with origin "Found from the cause" and no decision; the audit event `impact.records_found` is written and the revision rises. When nothing is added, nothing changes.
- The assessment changes none of the records it names.

## Related pages

- Impact assessment record
- New impact assessment (the rules for what is found)
