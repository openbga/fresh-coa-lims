---
title: Remove test from a draft specification version
urls: catalog:test_remove
views: catalog.views.test_remove
templates: catalog/form.html
models: catalog.SpecificationTest, catalog.SpecificationRevision
reviewed: 2026-11-10
---

## Purpose

Removes one test line from a draft specification version, recording why.

## Who can use it

- Sign-in required. **quality** role only; others receive 403 Forbidden.
- The **admin** role alone does not grant this page: opening or submitting it returns 403 Forbidden. An administrator who also holds the quality role acts with that role only, with no exception to the independence rules.
- The test must belong to the version in the URL, otherwise 404.
- Only drafts: for an approved or withdrawn version you are redirected back to the version with "Tests can only be removed from a draft version."

## Layout

- **Breadcrumbs**: Specifications and methods, specification code, "Version N", "Remove <test code>". Title: "Remove test <code> ·" and the version.
- **Intro**: "Removal from a draft is recorded in its history with your reason."
- **Record card**: Test, Criterion, Method.
- **Form**: Reason. Buttons **Cancel** and **Remove test**.

## Actions

| Action | Shown when | Who | Result |
|---|---|---|---|
| **Remove test** | Always on this page | Quality | Deletes the line; shows "Test <code> removed from draft <version>." and returns to the version |
| **Cancel** | Always | Quality | Returns to the version |

## Fields

| Field | Model field | Type / units | Required | Meaning and use |
|---|---|---|---|---|
| Test | `SpecificationTest.code`, `name` | Text | — | The line being removed. |
| Criterion | derived from limits | Text | — | Acceptance criterion in words and symbols. |
| Method | `SpecificationTest.method` | Method code | — | Method of the test. |
| Reason | audit event reason | Text, max 2000 | Yes | Why the test is removed. |
| Expected revision | — | Hidden integer | Yes | Record revision when the page opened. |

## Rules and hidden logic

- **Stale record**: "Record changed. Reload before removing this test." if the version changed since you opened the page.
- **Draft only**: "Tests can only be removed from a draft version." (page redirect) and "Only draft revisions can be changed." (server, if the version stopped being a draft meanwhile). Tests of approved or withdrawn versions are immutable at the database level.
- **Effect**: the line is deleted, the record revision increases by 1, and audit event `specification_revision.test_removed` keeps the removed line's content and your reason.
- Removing a test makes you an editor of the draft, so you can no longer approve this version.
- **Form behaviour**: the page shows "Fields marked * are required. The change is recorded in the audit trail with your reason." An invalid or refused submission returns the form with status 422, keeps your entries and shows an error summary ("Check the highlighted field(s) below. Your entries were kept.") plus refusals from the server as form-level errors.

## Related pages

- Specification version (record page).
