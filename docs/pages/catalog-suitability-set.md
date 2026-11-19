---
title: Suitability evidence of a method version
urls: catalog:suitability_set
views: catalog.evidence_views.suitability_set
templates: catalog/form.html
models: catalog.MethodRevision, catalog.MethodEvidence
reviewed: 2026-11-19
summary: Set what a draft method version relies on for its suitability: an approved evidence record of the method, or an external report only. Quality only; whoever sets it cannot approve the version.
---

## Common tasks

### Rely on an approved evidence record

1. Choose the [[Evidence record]].
2. Enter the [[Reason for change]] and select [[Save suitability evidence]]. The method record opens.

### Name an external report instead

1. Leave [[Evidence record]] on "None: an external reference only".
2. Choose the [[Suitability basis]], enter the [[Suitability evidence]] and the reason, then save.

## Good to know

- Whoever sets the suitability on a draft cannot approve that version.
- Only approved records of this method that conclude it is suitable are offered.
- Approval of the version checks the record again and is refused if it was withdrawn meanwhile.
- With a record chosen, the basis and reference come from the record and the fields below it are ignored.

## Purpose

Sets the suitability basis and evidence of a draft method version after it was created.

## Who can use it

- Sign-in required. **quality** role only; others receive 403. The role is checked before the version is looked up.
- A version that is not a draft redirects to the method record with "Suitability evidence can only be changed on a draft version."

## Layout

- **Header**: "Suitability evidence · <method> v<N>" with the introduction "Choose an approved evidence record of this method, or name a report kept elsewhere. Whoever changes a draft cannot approve it; approval checks the record again."
- **Record panel**: "Now" (the current record, or the kind and reference).
- **Form sections**: Evidence kept here, Or an external reference, Change control. Buttons **Cancel** and **Save suitability evidence**.

## Actions

| Action | Shown when | Who | Result |
|---|---|---|---|
| **Suitability evidence** (method record) | Draft version, quality | Quality | Opens this page |
| **Rely on it in version N** (evidence record) | Approved suitable record | Quality | Opens this page with the record chosen |
| **Save suitability evidence** | Draft | Quality | Saves; message "Suitability evidence of draft <version> set."; opens the method record |
| **Cancel** | Always | Quality | Returns to the method record |

## Fields

| Field | Model field | Type / units | Required | Meaning and use |
|---|---|---|---|---|
| Evidence record | `MethodRevision.evidence` | Choice | No | Approved records of this method concluding it is suitable, newest first. Its kind and report are used. |
| Suitability basis | `MethodRevision.suitability_kind` | Method validation, Compendial method verification, Method transfer, Documented fitness for intended use | Without a record | Only without an evidence record |
| Suitability evidence | `MethodRevision.suitability_ref` | Text, max 200 | Without a record | The report and where it is kept |
| Reason for change | audit reason | Text, max 2000 | Yes | Stored in the audit event |
| Expected revision (hidden) | `MethodRevision.revision` | Integer | Yes | Revision shown when the page opened |

## Rules and hidden logic

- **Preselection**: a record given in the address is chosen if it is offered. Otherwise a draft with no record starts with the record of the closest earlier version that relies on one, when that record is still offered. Otherwise the current record, or the current external reference, is shown.
- **Validations**: "Choose the kind of evidence." and "Name the report and where it is kept." without a record; a record that is of another method, withdrawn, not approved or concludes "Not suitable" is refused, with its identifier; "Nothing was changed."; "A reason is required."
- **Effect**: the version's record revision increases by 1; audit event `method_revision.suitability_set` with before and after (record, kind, reference) and your reason. Choosing a record replaces the kind and reference; choosing none clears the record.
- **Independence**: this counts as editing the draft.
- **Stale record**: "Record changed. Reload before saving." when the version changed after the page opened (checked under the version's lock).
- An external reference is not checked against withdrawn evidence records.
- **Approval**: approval refuses a version whose record is no longer approved, suitable and of the method, and freezes the record's identifier, kind, conclusion and content hash.

## Related pages

- Method record
- Method evidence record
- Approve method version
