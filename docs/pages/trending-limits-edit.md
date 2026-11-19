---
title: Change draft limits
urls: trending:limits_edit
views: trending.views.limits_edit
templates: catalog/form.html
models: trending.Limits, trending.Chart, core.AuditEvent
reviewed: 2026-11-19
summary: Change the figures, rules or basis of a draft limits version. Quality only. A computed draft is worked out again from its baseline. Whoever changes a draft cannot approve it.
---

## Common tasks

### Change a draft

1. Change the fields you need: the [[Limits]] basis, the baseline days, the figures, the [[Rules]] or the [[Basis of the limits]].
2. Enter the [[Reason for change]] and select [[Save draft]].

### Refresh a computed draft after its baseline changed

1. Select [[Save draft]] without changing the dates. The limits are worked out again from the results now in the baseline.
2. If nothing differs, the page says nothing was changed.

## Good to know

- Saving changes the revision. If someone else saved first, the page refuses with "Record changed. Reload before saving."
- Changing a draft makes you one of its authors: you cannot approve it afterwards.
- An approved version cannot be changed. The page sends you back to it and says to draft a new version.
- Saving with nothing different from the stored draft is refused with "Nothing was changed."

## Purpose

Changes a draft limits version before it is approved.

## Who can use it

- Sign-in required. **quality** role only; others, including admin alone, receive 403.

## Layout

- **Header**: title "Change draft · TC-n vN" and the same introduction as Draft limits.
- **Record** panel: Chart and Unit.
- **Form**: the sections and fields of Draft limits, filled with the draft's values, and a hidden expected revision. Buttons **Cancel** (to the limits record) and **Save draft**.

## Actions

| Action | Shown when | Who | Result |
|---|---|---|---|
| **Save draft** | Draft | Quality | Saves; message "Draft TC-n vN saved."; returns to the limits record |
| **Cancel** | Always | Quality | Returns to the limits record |

## Fields

| Field | Model field | Type / units | Required | Meaning and use |
|---|---|---|---|---|
| Limits, Baseline from, Baseline to, Center line, Standard deviation (σ), Lower limit, Upper limit, Rules, Results in a run, Results in a trend, Basis of the limits | `Limits` fields of those names | As on Draft limits | As on Draft limits | The draft's values; see Draft limits for meaning and ranges |
| Reason for change | audit reason | Text, max 2000 | Yes | Stored in the audit event |
| Expected revision (hidden) | `Limits.revision` | Integer | Yes | Revision shown when the page opened |

## Rules and hidden logic

- **Approved version**: opening the page for an approved version gives "TC-n vN is approved: draft a new version instead." and returns to the record.
- **Checks on saving** (under lock): the version is still a draft; the revision is unchanged ("Record changed. Reload before saving."); the same validations as Draft limits; and "Nothing was changed." when every value equals the stored one.
- **Effect**: the values are stored, the revision rises by 1 and the audit event `trend_limits.changed` records the before and after with your reason. A computed draft takes its center line, σ, limits and baseline results from the results in the baseline now.
- **Independence**: this audit event makes you an author of the draft, so you cannot approve it.

## Related pages

- Limits record
- Draft limits
- Approve limits
