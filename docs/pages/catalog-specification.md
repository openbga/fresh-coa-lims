---
title: Specification record
urls: catalog:specification
views: catalog.views.specification_detail
templates: catalog/specification_detail.html
models: catalog.Specification, catalog.SpecificationRevision, core.ElectronicSignature, core.AuditEvent
reviewed: 2026-11-17
summary: One specification: the material, stage and scope it applies to, every version with its status, effective period and approval, and its history.
---

## Common tasks
### Open a version and its tests
1. In [[Versions]], select a version number to see its tests, signatures and history.
### Start a new version
1. Select [[New version]]. It shows only to users with the quality role.
2. Enter the basis, effective period and reason on that page. The draft copies the tests of the latest version.
### See which version is in force
1. Under the title, read [[Approved]] with the version in force, or [[No approved version]] when none applies now.
## Good to know
- The version in force is the approved one that applies now. A newer approved version may not have started yet.
- Approving a later overlapping version retires an earlier one. The earlier version keeps its content and signature and shows Superseded.
- Lots keep the version frozen when their requirements were assigned.
- A scope other than general is an overlay: it applies in full beside the lot's other specifications and is never merged with them.
- Approved and withdrawn versions cannot be changed. Create a new version instead.

## Purpose

Shows one specification: what it applies to, all of its versions with status, effective period and signatures, and its own history.

## Who can use it

- Sign-in required. Viewing requires one of **analyst**, **reviewer**, **quality**, **admin** or **auditor**; others receive 403 Forbidden.
- **admin** without a laboratory role can view everything here but sees no create, edit, approval or signing controls. An administrator who also holds the lab role an action needs gets that action, under the same independence rules.
- **New version**: **quality** role only; the button is hidden for others.

## Layout

- **Breadcrumbs**: Specifications and methods, the specification code. Under the heading: **Approved** and "Version N in force" for the approved version in force now (the latest that applies at this moment), or **No approved version** when none applies; then the specification title.
- **Applicability**: Material, Stage, Scope. A scope other than "general" adds "(overlay: applies in full to a lot assigned under this scope, beside the specifications of the lot's other scopes; never merged with them)".
- **Versions** table, newest version first: Version (link), Status, Effective, Tests, Author, Approval.
- **Approval column**: each signature as one line: "Signed", the signer, the meaning, the time, "Record revision N" and the start of the content hash; "Not signed." when none.
- **History**: audit events of the specification and of all its versions (version creation, tests added or removed, approvals, withdrawals), oldest first, or the empty state "No recorded history".
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
| Scope | `Specification.scope` | Text | — | "general", or a named market or customer overlay. A lot is assigned under one or more scopes; the specification of each applies to it in full. |
| Version | `SpecificationRevision.version` | Integer | — | Version number within this specification. |
| Status | `SpecificationRevision.status` | Draft, Approved, Withdrawn | — | Only Approved versions can be used for lots. |
| Effective | `SpecificationRevision.effective_from`, `effective_until`, `superseded_from`, `superseded_by` | Date and time range | — | "start to end"; the end is exclusive. When a later version retired it, a second line reads "Superseded by version N from <time>", or "Superseded by version N before it took effect" when it never applied. |
| Tests | — | Count | — | Number of test lines on the version. |
| Author | `SpecificationRevision.author` | User | — | Who created the version (full name, else username). |

## Rules and hidden logic

- **Order**: versions are listed by version number, newest first; the History list is oldest first.
- **Scope and lots**: when a lot's requirements are assigned under this specification's scope, its version in force applies to the lot in full, beside the specifications of the lot's other scopes. Nothing is merged: a test stated alike is one requirement, and a test stated differently holds the lot until quality signs which requirement applies (Decide conflicting requirements, or Replace lot requirements once testing has started).
- **History**: includes the events of every version of this specification as well as its own, oldest first.
- **Immutability**: approved and withdrawn versions cannot be changed at the database level; a draft's header content is fixed at creation.
- **Effective intervals** are half-open (start inclusive, end exclusive). The version used for new lots is the approved one that applies now: inside its period and not superseded. Approving a later version whose period overlaps an approved one retires the earlier one from the later of the new version's start and the moment of approval (never retroactively); the earlier version keeps its approved content and signature. Approving a draft that overlaps an approved version numbered after it is refused. Lots keep the versions frozen for them.
- Audit action names are shown as stored (for example `specification.created`).

## Related pages

- [Specifications](/catalog/)
- Specification version (record page), New version.
- [Materials](/catalog/materials/)
