---
title: Place hold
urls: impact:hold
views: impact.views.record_hold
templates: catalog/form.html
models: impact.Item, stability.Hold, quality.Lot, core.AuditEvent
reviewed: 2026-11-17
summary: Place a quality hold on an affected lot through the assessment. It blocks the lot's QC disposition and its certificates until a different quality person releases it. Quality only.
---

## Common tasks

### Hold an affected lot

1. On the assessment, select [[Place hold]] in the lot's row.
2. Enter [[Why the lot is held]] and select [[Place hold]].

### Release the hold later

1. Open the hold from the Hold column. A quality person who did not place it signs the release there.

## Good to know

- While the hold is active, the lot's QC disposition cannot be signed and no certificate is issued or amended for it.
- A lot record in the assessment takes one hold. When it exists the row shows its identifier and state instead of the link.
- You cannot release a hold you placed, and you cannot conclude an assessment in which you placed one.
- An assessment cannot be withdrawn while a hold placed through it is active.

## Purpose

Places the lot's protective quality hold from an impact assessment, referenced to it, so the lot's QC disposition cannot be signed and no certificate is issued or amended for it while the effect is judged.

## Who can use it

- Sign-in required. **quality** role only; others receive 403.
- An assessment that is no longer open redirects to its record with "This impact assessment is no longer open."

## Layout

- Breadcrumbs (Impact assessments, IA-n, Place hold), the introduction, the facts Assessment, Lot, Now and Why it is in the assessment, the form, **Cancel** and **Place hold** (a red, destructive button).

## Actions

| Action | Shown when | Who | Result |
|---|---|---|---|
| **Place hold** | The record is a lot that has no hold and is not cancelled | Quality | Creates the hold; message "<hold> placed on lot <number>."; returns to the assessment |
| **Cancel** | Always | Quality | Returns without saving |

## Fields

| Field | Model field | Type / units | Required | Meaning and use |
|---|---|---|---|---|
| Why the lot is held | `Hold.reason`, audit reason | Text, max 2000 | Yes | Stored on the hold |
| Expected revision (hidden) | `Item.revision` | Integer | Yes | The record's revision when the page opened |

## Rules and hidden logic

- **Refusals** (message and return to the assessment): "A hold is placed on a lot." for a record that is not a lot; "<hold> was placed through this assessment." when the record has one; "The lot was cancelled; it takes no hold."; "Say why the lot is held." when the reason is empty.
- **The hold** is the lot's ordinary quality hold (kind Quality). Its reference is "IA-n · <quality-system reference>" (just "IA-n" when there is none).
- **Effect**: the hold, the link from the record, the audit events `hold.placed` and `impact.hold_placed`, and the revisions of the record and the assessment are committed together. A stale page is refused with "The record changed since you opened it. Reload and review."
- **Release**: on the hold's page, by a quality person other than the one who placed it, with a signature. Concluding the assessment leaves active holds in place.
- **Independence**: whoever places a hold cannot conclude the assessment.
- The hold does not change the lot's record, signed disposition or an issued certificate. Withdrawing a certificate is done on the certificate's own page.

## Related pages

- Impact assessment record
- Hold record (release)
