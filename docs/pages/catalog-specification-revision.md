---
title: Specification version
urls: catalog:specification_revision
views: catalog.views.specification_revision
templates: catalog/specification_revision.html
models: catalog.SpecificationRevision, catalog.SpecificationTest, core.ElectronicSignature, core.AuditEvent
reviewed: 2026-11-10
---

## Purpose

One version of a specification: its facts, the tests and acceptance criteria, signatures and history. Quality users build the draft here and send it for independent approval.

## Who can use it

- Sign-in required. Viewing requires one of **analyst**, **reviewer**, **quality**, **admin** or **auditor**; others receive 403 Forbidden.
- **admin** without a laboratory role can view everything here but sees no create, edit, approval or signing controls. An administrator who also holds the lab role an action needs gets that action, under the same independence rules.
- **Add test**, **Withdraw draft**, test **Remove**: **quality** role, drafts only.
- **Review and approve**: quality role, draft, and only if you did not author or edit it.
- Controls are shown from the role and state only; the server rechecks every action.

## Layout

- **Breadcrumbs**: Specifications and methods, specification code, "Version N". Under the heading: status, "record revision N" and the specification title.
- **Alerts**: "Independent approval" ("You authored or edited this draft, so another quality approver must sign it.") for quality users on a draft they cannot approve; "Frozen" for approved versions ("This approved version and its tests cannot be changed. Content hash" and the full hash).
- **Version facts**: Material, Stage and scope, Effective, Basis, Author, Reason for version.
- **Tests and acceptance criteria**: table with #, Test (code and name), Method (link), Acceptance criterion, Rounding, Replication, Required, and **Remove** for draft editors. Empty state "No tests yet" ("Approval requires at least one test with an approved method.") with an **Add test** button for quality.
- **Signatures**: signer, meaning, time, record revision, hash, or "Not signed."
- **History**: attributed audit events for this version only (not the specification's), oldest first, or "No recorded history."
- **Foot line**: the version identifier, when the page was viewed and by whom.

## Actions

| Action | Shown when | Who | Result |
|---|---|---|---|
| **Add test** | Draft | Quality | Opens the Add test form |
| **Withdraw draft** | Draft | Quality | Opens the Withdraw page |
| **Review and approve** | Draft and you are independent of its author and editors | Quality | Opens the Approve page |
| **Remove** (on a test row) | Draft | Quality | Opens the Remove test form |
| Method link | Always | Any viewer | Opens that method |

## Fields

| Field | Model field | Type / units | Required | Meaning and use |
|---|---|---|---|---|
| Status | `SpecificationRevision.status` | Draft, Approved, Withdrawn | — | Only Approved versions are used for lots. |
| Record revision | `SpecificationRevision.revision` | Integer | — | Increases on every test change, approval and withdrawal; signatures bind to it. |
| Effective | `SpecificationRevision.effective_from`, `effective_until` | Date and time range | — | End exclusive. |
| Basis | `SpecificationRevision.basis` | Text | — | Basis of the limits. |
| Reason for version | `SpecificationRevision.change_reason` | Text | — | Reason given when the version was created. |
| # | `SpecificationTest.position` | Integer | — | Display order. |
| Test | `SpecificationTest.code`, `name` | Text | — | Test code and name. |
| Acceptance criterion | limits or `expected_text` | Decimal range with unit, or text | — | For example "98 – 102 %"; "≥", ">", "≤", "<" for one-sided limits; "(exclusive bound)" when a bound is exclusive. |
| Rounding | `SpecificationTest.reporting_decimals` | Integer | — | "N decimals" or "Exact". |
| Replication | `replicates`, `replicate_limits`, `max_retests` | Integers | — | "N replicates", ", each within limits" when more than one and enforced, then "up to N retests" or "no retests". |
| Required | `SpecificationTest.required` | Yes/No | — | "Required" or "Information only". |

## Rules and hidden logic

- **Draft only changes**: tests can be added or removed only while the version is Draft. Approved and withdrawn versions and their tests are immutable at the database level.
- **Revision**: each test added or removed increases the record revision by 1.
- **Approval prerequisites** (checked at signing, not on this page): at least one test; every test's method has an approved method version effective at the specification's start; no overlap with another approved version of this specification.
- **Independence**: the author, or anyone who made another change to the draft (any audit event on it other than a signature), cannot approve it. Quality users in that position see the "Independent approval" alert instead of the approve button.
- **Approval**: signature meaning "approved", binds the record revision, stores a content hash (see the Approve page).
- **Withdrawn** versions show Withdrawn and no action buttons.
- Audit actions are listed as stored, for example `specification_revision.test_added`.

## Related pages

- Specification (record page).
- [Methods](/catalog/methods/)
- Add test, Remove test, Approve specification, Withdraw draft.
- Sampling lot page: links here from frozen requirements.
