---
title: Specification record
urls: catalog:specification
views: catalog.views.specification_detail
templates: catalog/specification_detail.html
models: catalog.Specification, catalog.SpecificationRevision, core.ElectronicSignature, core.AuditEvent
reviewed: 2026-11-10
---

## Purpose

Shows one specification: what it applies to, all of its versions with status, effective period and signatures, and its own history.

## Who can use it

- Sign-in required. Viewing requires one of **analyst**, **reviewer**, **quality**, **admin** or **auditor**; others receive 403 Forbidden.
- **New version**: **quality** role only; the button is hidden for others.

## Layout

- **Breadcrumbs**: Specifications and methods, the specification code. The specification title is shown under the heading.
- **Applicability**: Material, Stage, Scope. A scope other than "general" adds "(overlay; never merged with other scopes)".
- **Versions** table, newest version first: Version (link), Status, Effective, Tests, Author, Approval.
- **Approval column**: each signature as "Signed", signer name, meaning, time, "record revision N" and a shortened content hash; "Not signed." when none.
- **History**: audit events of the specification and of all its versions (version creation, tests added or removed, approvals, withdrawals), oldest first, or "No recorded history."
- **Foot line**: identifier and when the page was viewed and by whom.

## Actions

| Action | Shown when | Who | Result |
|---|---|---|---|
| **New version** | Viewer has the quality role | Quality | Opens the New version form |
| "Version N" link | Always | Any viewer | Opens the version page with tests, signatures and history |

## Fields

| Field | Model field | Type / units | Required | Meaning and use |
|---|---|---|---|---|
| Material | `Specification.material` | "code · name" | — | Material covered. |
| Stage | `Specification.stage` | Choice label | — | Stage covered. |
| Scope | `Specification.scope` | Text | — | General or named overlay. |
| Version | `SpecificationRevision.version` | Integer | — | Version number within this specification. |
| Status | `SpecificationRevision.status` | Draft, Approved, Withdrawn | — | Only Approved versions can be used for lots. |
| Effective | `SpecificationRevision.effective_from`, `effective_until` | Date and time range | — | "start to end"; the end is exclusive. |
| Tests | — | Count | — | Number of test lines on the version. |
| Author | `SpecificationRevision.author` | User | — | Who created the version (full name, else username). |

## Rules and hidden logic

- **Order**: versions are listed by version number, newest first; the History list is oldest first.
- **History**: includes the events of every version of this specification as well as its own, oldest first.
- **Immutability**: approved and withdrawn versions cannot be changed at the database level; a draft's header content is fixed at creation.
- **Effective intervals** are half-open (start inclusive, end exclusive) and approved versions of one specification may not overlap.
- Audit action names are shown as stored (for example `specification.created`).

## Related pages

- [Specifications](/catalog/)
- Specification version (record page), New version.
- [Materials](/catalog/materials/)
