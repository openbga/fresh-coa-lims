---
title: Add suitable resource to a method version
urls: catalog:method_resource_new
views: catalog.views.method_resource_new
templates: catalog/form.html
models: catalog.MethodResource, catalog.MethodRevision
reviewed: 2026-11-19
summary: List an instrument category, reagent, reference standard or prepared solution as suitable for a draft method version. Only a draft can be changed.
---

## Common tasks
### List a suitable resource
1. In [[Name in the register]], choose an equipment category or a lot name, grouped by kind.
2. Leave [[Recorded with every result]] ticked when every result must record one, or clear it when it may be used but is not needed.
3. For an instrument, tick [[Qualified for the method]] when it also needs a qualification for this method.
4. Give the [[Reason for change]] and select [[Add suitable resource]]. The method record opens.
### Leave without adding
1. Select [[Cancel]] to return to the method record.
## Good to know
- Once a version lists a kind, results under it accept only the listed resources of that kind, and solutions prepared from them. A kind with no line stays open. Fitness checks still apply.
- Adding a line makes you an editor of the draft, so you can no longer approve it.
- A version lists at most 20 resources, and each kind and name only once, whatever the case.
- Approval freezes the lines. A new version copies them.

## Purpose

Adds one instrument category, reagent, reference standard or prepared solution to the resources a draft method version lists as suitable.

## Who can use it

- Sign-in required. **quality** role only; others receive 403 Forbidden.
- The **admin** role alone does not grant this page: opening or submitting it returns 403 Forbidden. An administrator who also holds the quality role acts with that role only, with no exception to the independence rules.
- Only draft versions. Otherwise you are redirected to the method with a message that suitable resources can only be changed on a draft version.

## Layout

- **Breadcrumbs**: Specifications and methods, Methods, method code, "Version N · Add suitable resource". Title: "Add suitable resource ·" and the version.
- **Intro**: what listing does at result entry (see Good to know).
- **Form sections**: Suitable resource, Change control.
- **Buttons**: **Cancel** and **Add suitable resource**.

## Actions

| Action | Shown when | Who | Result |
|---|---|---|---|
| **Add suitable resource** | Draft version | Quality | Adds the line; shows "<kind>: <name> listed as suitable for <version>." and returns to the method |
| **Cancel** | Always | Quality | Returns to the method |

## Fields

| Field | Model field | Type / units | Required | Meaning and use |
|---|---|---|---|---|
| Name in the register | `MethodResource.kind`, `name` | Choice grouped by Instrument, Reagent, Reference standard, Prepared solution | Yes | An instrument is listed by its equipment category; the others by the name their lots carry. Only names the laboratory register already holds are offered. |
| Recorded with every result | `MethodResource.required` | Checkbox, ticked by default | No | Every result and batch QC entry must record one. Otherwise it may be used. |
| Qualified for the method | `MethodResource.method_qualified` | Checkbox | No | Instruments only: the instrument also needs an approved, current qualification whose activity is this method's code. |
| Reason for change | audit event reason | Text, max 2000 | Yes | Stored in the audit event. |

## Rules and hidden logic

- **Validations**: "Only an instrument can be asked to be qualified for the method." for a line of another kind; "No equipment category of this kind in the laboratory register is named like this." (or "No lot name ...") when the name is not in the register; "This version already lists it." for the same kind and name in any case; "A method version lists at most 20 suitable resources." The database also refuses a duplicate, a qualification request on a non-instrument and a twenty-first line. The name is kept as the register first recorded it.
- **Effect**: the record revision increases by 1; audit event `method_revision.resource_added` with the line and your reason. Adding a line makes you an editor, so you can no longer approve this version.
- **Immutability**: lines are only added or removed on a draft, never updated; the database refuses changes after approval.
- **At result entry** (observation, correction, file import, batch QC): every instrument selected must be of a listed category; a lot of a kind the version lists, or prepared from a lot of such a kind, must answer one of its lines, itself or through a lot it was prepared from (a version that lists only its reference standard leaves solvents open but checks the solutions prepared from standards); every required line must be answered; an instrument whose line asks for it needs an approved, current qualification whose activity is the method code. Refusals come together with the calibration, service, release and expiry refusals, nothing is stored, and the refusal is audited (`resource.use_blocked`). Names are compared without case or repeated spaces. Tests frozen to an earlier version keep that version's lines.
- **Form behaviour**: the page shows "Fields marked * are required. The change is recorded in the audit trail with your reason." An invalid or refused submission returns the form with status 422, keeps your entries and shows an error summary ("Check the highlighted field(s) below. Your entries were kept.") plus refusals from the server as form-level errors.

## Related pages

- Method (record page).
- Remove suitable resource, Equipment qualification.
