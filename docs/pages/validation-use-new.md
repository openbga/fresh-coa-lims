---
title: Record intended use
urls: validation:use_new
views: validation.views.use_new
templates: catalog/form.html
models: validation.UseAcceptance, core.AuditEvent
reviewed: 2026-11-17
summary: Record the laboratory's intended use of the system for acceptance: what it is used for, the supported assays, the owners and the validation report. Recording accepts nothing.
---

## Common tasks
### Record the intended use
1. Fill in [[Title]] and [[Intended use]], then tick each method the laboratory validated for this use in [[Supported assays]].
2. Choose the [[Process owner]] and the [[System owner]].
3. Name the [[Validation report]] with its revision. Add the [[Validation report link]] if there is one.
4. Give a [[Reason]] and select [[Record intended use]]. A different quality person then accepts it from the record.
### Record what the system is not used for
1. Describe functions the laboratory does not use, and records it keeps elsewhere, in [[Outside the intended use]].
2. List issues found in validation, and how each is resolved or restricted, in [[Known issues and conditions]].
### Leave without recording
1. Select [[Cancel]] to return to the list. Nothing is recorded.
## Good to know
- Only methods with an approved version in force can be chosen. If none is in force, the page says so: approve the methods first.
- Owners must be active accounts holding the analyst, reviewer, quality or admin role.
- You cannot accept a record you recorded. A different quality person must sign it.
- Recorded content is never edited. To correct a record, withdraw it and record a new one.
- The acceptance signature, not this page, freezes the approved configuration in force and the running release.

## Purpose

Record the laboratory's intended use of the system for acceptance: what it is used for, the supported assays, who owns the process and the system, and the validation report. Recording accepts nothing; a different Quality person accepts it with a signature.

## Who can use it

- Sign-in required. Role: Quality. Others, including an account holding only the Admin role, receive 403.
- The record is not signed. The recorder cannot accept it later.

## Layout

- Breadcrumbs (Validation, Record intended use), an introduction, and the form in four groups: **Intended use**, **Responsibilities**, **Validation evidence**, **Change control**; then **Cancel** and **Record intended use**.
- When no method has an approved version in force, a fact "Supported assays: No method has an approved version in force. Approve the methods first." is shown and no assay can be chosen.

## Actions

| Action | Shown when | Who | Result |
|---|---|---|---|
| **Record intended use** | Always | Quality | Creates the record awaiting acceptance; shows "UA-n recorded; a different quality person accepts it." and opens the record. Refusals appear as errors with your entries kept (status 422) |
| **Cancel** | Always | Quality | Returns to the list |

## Fields

| Field | Model field | Type / units | Required | Meaning and use |
|---|---|---|---|---|
| Title | `UseAcceptance.title` | Text, max 160 | Yes | Short name of the use |
| Intended use | `UseAcceptance.intended_use` | Text, max 4000 | Yes | Materials, stages, records and decisions the system supports |
| Outside the intended use | `UseAcceptance.exclusions` | Text, max 4000 | No | Functions not used, and records kept elsewhere |
| Supported assays | `UseAcceptance.method_codes` | Checkboxes | Yes, at least one | Only methods with an approved version in force are listed, as "title (code)". The acceptance freezes that version |
| Process owner | `UseAcceptance.process_owner` | User | Yes | Responsible for the business process |
| System owner | `UseAcceptance.system_owner` | User | Yes | Responsible for availability, maintenance and data security |
| Other responsibilities | `UseAcceptance.other_responsibilities` | Text, max 4000 | No | Others named, such as key users |
| Validation report | `UseAcceptance.validation_ref` | Text, max 200 | Yes | The laboratory's report, with its revision |
| Validation report link | `UseAcceptance.validation_url` | Web address, max 500 | No | Must be an http or https address |
| Known issues and conditions | `UseAcceptance.open_issues` | Text, max 4000 | No | Issues found and how each is resolved or restricted |
| Reason | `AuditEvent.reason` | Text, max 2000 | Yes | Recorded in the audit trail |

## Rules and hidden logic

- Owners must be active accounts holding the Analyst, Reviewer, Quality or Admin role; otherwise "Choose an active account that holds a working role." These roles are listed as a choice only; the system does not check that an owner agrees.
- Supported assays are checked again on saving: "Select at least one supported assay."; at most 200; a code with no approved version in force: "<code> has no approved version in force. Choose methods that are in force."
- Title, intended use and validation report may not be blank; the database refuses blanks.
- Effect: one transaction creates the record in state **Awaiting acceptance** at revision 1 and writes the audit event `use_acceptance.recorded` with your reason. The configuration is not frozen yet.
- Recorded content is never edited. To correct a record, withdraw it and record a new one.

## Related pages

- [Intended use](/validation/) (Cancel returns here)
- Intended use record (opened after saving)
