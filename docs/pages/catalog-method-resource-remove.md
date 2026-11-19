---
title: Remove suitable resource from a method version
urls: catalog:method_resource_remove
views: catalog.views.method_resource_remove
templates: catalog/form.html
models: catalog.MethodResource, catalog.MethodRevision
reviewed: 2026-11-19
summary: Remove one suitable instrument category, reagent, reference standard or prepared solution from a draft method version. Your reason is recorded in the version's history.
---

## Common tasks
### Remove the line
1. Check the kind, name and use under [[Record]].
2. Explain why in [[Reason]], then select [[Remove]]. The method record opens.
### Keep the line
1. Select [[Cancel]].
## Good to know
- Removing a line makes you an editor of the draft, so you can no longer approve it.
- Without a line of a kind, results recorded under the version accept any resource of that kind that passes the fitness checks.
- The removed line stays in the history with your reason.
- If someone changes the draft after you open this page, removal is refused. Reload and try again.

## Purpose

Removes one suitable resource from a draft method version, recording why.

## Who can use it

- Sign-in required. **quality** role only; others receive 403 Forbidden.
- The **admin** role alone does not grant this page: opening or submitting it returns 403 Forbidden. An administrator who also holds the quality role acts with that role only, with no exception to the independence rules.
- The line must belong to the version in the URL, otherwise 404.
- Only drafts: for an approved or withdrawn version you are redirected back to the method with "Suitable resources can only be removed from a draft version."

## Layout

- **Breadcrumbs**: Specifications and methods, Methods, method code, "Version N · Remove <name>". Title: "Remove <name> ·" and the version.
- **Intro**: "Removal from a draft is recorded in its history with your reason."
- **Record card**: Kind, Name, "Recorded with every result" (Yes, or "No, may be used").
- **Form**: Reason. Buttons **Cancel** and **Remove**.

## Actions

| Action | Shown when | Who | Result |
|---|---|---|---|
| **Remove** | Always on this page | Quality | Deletes the line; shows "<kind>: <name> removed from draft <version>." and returns to the method |
| **Cancel** | Always | Quality | Returns to the method |

## Fields

| Field | Model field | Type / units | Required | Meaning and use |
|---|---|---|---|---|
| Kind | `MethodResource.kind` | Text | — | Instrument, Reagent, Reference standard or Prepared solution. |
| Name | `MethodResource.name` | Text | — | The equipment category or lot name. |
| Recorded with every result | `MethodResource.required` | Yes / No | — | Whether the line had to be answered at result entry. |
| Reason | audit event reason | Text, max 2000 | Yes | Why the line is removed. |
| Expected revision | — | Hidden integer | Yes | Record revision when the page opened. |

## Rules and hidden logic

- **Stale record**: "The version changed. Reload before removing this line."
- **Draft only**: "Only draft revisions can be changed." if the version stopped being a draft meanwhile.
- **Effect**: record revision increases by 1; audit event `method_revision.resource_removed` keeps the removed line and your reason.
- **Immutability**: the database refuses removal once the version is no longer a draft.
- **Form behaviour**: the page shows "Fields marked * are required. The change is recorded in the audit trail with your reason." An invalid or refused submission returns the form with status 422, keeps your entries and shows an error summary ("Check the highlighted field(s) below. Your entries were kept.") plus refusals from the server as form-level errors.

## Related pages

- Method (record page).
- Add suitable resource.
