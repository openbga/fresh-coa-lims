---
title: Method record
urls: catalog:method
views: catalog.views.method_detail
templates: catalog/method_detail.html
models: catalog.Method, catalog.MethodRevision, catalog.MethodQCCheck, core.ElectronicSignature, core.AuditEvent
reviewed: 2026-11-10
---

## Purpose

Shows a method with every version: procedure, suitability evidence, batch QC checks, signatures and history. Quality users manage drafts here.

## Who can use it

- Sign-in required. Viewing requires one of **analyst**, **reviewer**, **quality**, **admin** or **auditor**; others receive 403 Forbidden.
- **New version**, **Withdraw draft**, **Add QC check**, QC check **Remove**: **quality** role only (drafts only for the last three).
- **Review and approve**: quality, draft, and only when you did not author or edit that version. Otherwise the text "Another quality approver must sign this draft." is shown instead.

## Layout

- **Breadcrumbs**: Specifications and methods, Methods, method code. The method title is under the heading.
- **One card per version**, newest first: heading "Version N" with its status; draft buttons for quality; facts Technique, Summary (only when entered), Controlled procedure, Suitability, Effective, QC batch ("Runs in a QC batch" or "No batch QC required"), Record revision, Author.
- **Batch QC checks** (batch methods only): table Check, "Limits (inclusive)", with **Remove** on drafts for quality. Empty: "No QC checks yet. Approval requires at least one." **Add QC check** on drafts for quality.
- **Signatures** under each version: signer, meaning, time, record revision, hash, or "Not signed."
- **Empty state**: "No versions" ("Create the first version of this method.").
- **History**: audit events for the method and all its versions (including QC check changes), oldest first.

## Actions

| Action | Shown when | Who | Result |
|---|---|---|---|
| **New version** | Quality role | Quality | Opens the New version form |
| **Withdraw draft** | Version is Draft, quality role | Quality | Opens the Withdraw page |
| **Review and approve** | Draft, quality, independent of author and editors | Quality | Opens the Approve page |
| **Add QC check** | Draft batch version, quality | Quality | Opens the Add QC check form |
| **Remove** (QC check) | Draft, quality | Quality | Opens the Remove QC check form |

## Fields

| Field | Model field | Type / units | Required | Meaning and use |
|---|---|---|---|---|
| Technique | `MethodRevision.technique` | Text | — | Analytical technique. |
| Summary | `MethodRevision.summary` | Text | — | Free description of the method; shown only when the version has one. |
| Controlled procedure | `MethodRevision.document_ref` | Text | — | Procedure document and revision. |
| Suitability | `MethodRevision.suitability_kind`, `suitability_ref` | "kind · evidence reference" | — | Basis and evidence of suitability. |
| Effective | `MethodRevision.effective_from`, `effective_until` | Date and time range | — | End exclusive. |
| QC batch | `MethodRevision.requires_batch` | Yes/No text | — | Whether results must come from a batch whose QC checks pass. |
| Record revision | `MethodRevision.revision` | Integer | — | Increases with QC check changes, approval and withdrawal. |
| Author | `MethodRevision.author` | User | — | Who created the version. |
| Check | `MethodQCCheck.code`, `name` | Text | — | QC check identifier and name. |
| Limits (inclusive) | `MethodQCCheck.lower_limit`, `upper_limit`, `unit` | Decimal with unit | — | "≥ low and ≤ high unit". |

## Rules and hidden logic

- **Order**: versions newest first; history oldest first.
- **Immutability**: approved and withdrawn versions, and their QC checks, are immutable at the database level.
- **Not shown here**: the reason for change appears only in the audit history.
- **Effective intervals** are half-open and approved versions of one method may not overlap.
- **Independence**: author and anyone who changed the draft cannot approve it.
- Audit actions are shown as stored, for example `method_revision.qc_check_added`.

## Related pages

- [Methods](/catalog/methods/)
- New version, Approve method, Withdraw draft, Add QC check, Remove QC check.
- Specification version pages list this method for each test.
