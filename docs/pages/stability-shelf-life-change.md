---
title: Change draft evaluation
urls: stability:shelf_life_change
views: stability.shelf_life_views.shelf_life_change
templates: ops/form.html
models: stability.ShelfLifeEvaluation, stability.ShelfLifeStudy, core.AuditEvent
reviewed: 2026-11-19
summary: Change which studies a draft shelf-life evaluation uses, its expected change or its purpose. Quality only. Whoever changes a draft cannot conclude it.
---

## Common tasks

### Leave a study out or add one back

1. Clear or tick studies in [[Studies]].
2. Enter the [[Reason]] and select [[Save changes]].

### Change the expected change or the purpose

1. Choose the [[Expected change]] or edit the [[Purpose]].
2. Enter the [[Reason]] and select [[Save changes]].

## Good to know

- The test, storage condition and acceptance criterion are fixed. For another, withdraw the draft and draft a new evaluation.
- Whoever changes a draft cannot conclude it.
- Saving with nothing different is refused with "Nothing was changed."
- Only a draft changes. A concluded or withdrawn evaluation sends you back to its record with a message.

## Purpose

Adjusts a draft before it is concluded, for example to leave out a study that does not belong in the evaluation. The laboratory decides which studies to use.

## Who can use it

- Sign-in required. **quality** role only; others receive 403.

## Layout

- Breadcrumbs (Stability and retention, Shelf-life evaluations, SLE-n, Change), title "Change SLE-n", an introduction, the form, **Cancel** and **Save changes**.

## Actions

| Action | Shown when | Who | Result |
|---|---|---|---|
| **Save changes** | Draft | Quality | Saves; message "SLE-n changed."; returns to the record |
| **Cancel** | Always | Quality | Returns to the record |

## Fields

| Field | Model field | Type / units | Required | Meaning and use |
|---|---|---|---|---|
| Studies | `ShelfLifeStudy` | Checkboxes | Yes | Studies of the protocol code in this container closure, labelled with study, lot and protocol. At least one, at most 20. The primary batches, at least three where data exist |
| Expected change | `direction` | Choice | Yes | As when drafting. Refused when the test lacks the limit it needs |
| Purpose | `purpose` | Text, max 2000 | Yes | Why the shelf life is evaluated |
| Reason | audit reason | Text, max 2000 | Yes | Recorded in the history |
| Expected revision (hidden) | `revision` | Integer | Yes | Revision shown when the page opened |

## Rules and hidden logic

- **Stale record**: "Record changed. Reload before saving." when the revision moved.
- **Validations**: "Choose at least one study."; "An evaluation uses at most 20 studies."; "Choose studies of protocol <code> in <container closure>."; "State why the shelf life is evaluated."
- **Effect**: studies added or removed, revision raised, audit event `shelf_life.changed` with before and after.
- **Independence**: the change makes you a drafter; you cannot conclude the evaluation afterwards.
- **Not draft**: "SLE-n is <state>: it no longer changes."

## Related pages

- Evaluation record
- [Shelf-life evaluations](/stability/shelf-life/)
