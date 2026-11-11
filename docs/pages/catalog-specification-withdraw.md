---
title: Withdraw specification draft
urls: catalog:specification_withdraw
views: catalog.views.specification_withdraw
templates: catalog/form.html
models: catalog.SpecificationRevision
reviewed: 2026-11-10
---

## Purpose

Withdraws a draft specification version that will not be approved, with a recorded reason. The draft stays in the history.

## Who can use it

- Sign-in required. **quality** role only; others receive 403 Forbidden. The role is checked before the record is looked up, so a user without it gets 403 for existing and non-existent IDs alike; quality users get 404 for a missing ID.
- No independence rule applies: the author or an editor of the draft may withdraw it.
- Only drafts: for an approved or withdrawn version you are redirected back with "Only draft revisions can be withdrawn."

## Layout

- **Breadcrumbs**: Specifications and methods, specification code, "Version N", Withdraw. Title: "Withdraw draft" and the version.
- **Intro**: "A withdrawn draft stays in the history and can no longer be edited or approved. Create a new version to continue."
- **Form**: Reason. Buttons **Cancel** and **Withdraw draft** (red).

## Actions

| Action | Shown when | Who | Result |
|---|---|---|---|
| **Withdraw draft** | Draft version | Quality | Withdraws the draft; shows "Draft <version> withdrawn." and returns to the specification version |
| **Cancel** | Always | Quality | Returns without change |

## Fields

| Field | Model field | Type / units | Required | Meaning and use |
|---|---|---|---|---|
| Reason | — | Text, max 2000 | Yes | Why the draft is withdrawn; stored in the audit event. |
| Expected revision | — | Hidden integer | Yes | Record revision shown when the page opened. |

## Rules and hidden logic

- **Draft only**: "Only draft revisions can be withdrawn." (page redirect and server).
- **Stale record**: "Record changed. Reload before withdrawing." if someone changed the draft since you opened the page.
- **Effect**: status becomes Withdrawn and the record revision increases by 1. Audit event `revision.withdrawn` with before and after snapshots and your reason. No electronic signature is created.
- **Approved versions cannot be withdrawn** here; they are immutable. Create a new version instead.
- **Where the control is shown**: the version page shows **Withdraw draft** to quality users on drafts.
- A failed submission returns status 422 and keeps your entries.

## Related pages

- The specification version.
