---
title: Approve specification version
urls: catalog:specification_approve
views: catalog.views.specification_approve
templates: catalog/approve.html
models: catalog.SpecificationRevision, core.ElectronicSignature, core.PINCredential
reviewed: 2026-11-10
---

## Purpose

Independent review and electronic signature that approves a draft specification version. Approval freezes it so it can be used for lots.

## Who can use it

- Sign-in required. **quality** role only; others receive 403 Forbidden. Reading roles other than quality cannot open this page.
- The signer must not be the author and must not have edited the draft (any earlier audit event on this version by you other than a signature). Then the page opens with status 403 and an explanation, and no form.
- Administrators get no exception: "Independent approval cannot be bypassed by any role, including administrators."
- The signing username you type must equal your signed-in username.

## Layout

- **Breadcrumbs**: Specifications and methods, specification code, "Version N", Approve.
- **Header line**: the version, "record revision N" and its status.
- **Content being approved**: Material, Stage and scope, Effective, Basis, Author, and the tests table (or "No tests yet. Approval requires at least one test.").
- **Sign approval**: the statement of what your signature means ("approved", the record revision, the resulting revision and a content hash), "Signer:" with your name and username, and a link "Enroll or change your signature PIN".
- **Form**: Approval comment, Signing username, Signature PIN. Buttons **Cancel** and **Sign and approve**.
- **Blocked state**: an alert "Not permitted" with the reason, and a button "Back to <version>" instead of the form.

## Actions

| Action | Shown when | Who | Result |
|---|---|---|---|
| **Sign and approve** | Version is a draft and you are an independent quality user | Quality, not author or editor | Verifies your PIN, approves and signs; shows "Specification <version> approved and signed." and returns to the specification version |
| **Cancel** | Form shown | Quality | Returns without signing |
| Enroll or change your signature PIN | Form shown | Signer | Opens the Signature PIN page |

## Fields

| Field | Model field | Type / units | Required | Meaning and use |
|---|---|---|---|---|
| Approval comment | `AuditEvent.reason` | Text, max 2000 | Yes | Help: "What you checked before approving." |
| Signing username | — | Text, max 150 | Yes | Must match your signed-in username. |
| Signature PIN | — | Password (digits) | Yes | Your signature PIN; never stored or logged, re-entered every time. |
| Expected revision | — | Hidden integer | Yes | Record revision shown when the page opened; signing fails if it changed. |

## Rules and hidden logic

- **Draft only**: "Only draft revisions can be approved." (shown on the page as "Not permitted", and by the server).
- **Independence**: "You authored this revision; another quality approver must sign." or "You edited this draft; another quality approver must sign." The server rechecks at signing.
- **Stale record**: "Record changed. Reload and review before signing." if the record revision differs from the one shown.
- **Content checks at approval**: "Add at least one test before approval." and "No approved method revision is effective at the specification start: <method codes>" (each test's method needs an approved version effective at the specification's start time; only the start is checked); numeric/qualitative shape rules are rechecked.
- **No overlap**: "Effective dates overlap an approved version." Effective intervals are half-open (start inclusive, end exclusive); an approved version of the same record that overlaps blocks approval. Approvals are serialised by a database lock so two approvals cannot race.
- **Signature and audit**: signature meaning is "approved". The version becomes Approved, its content snapshot and SHA-256 hash are stored, the record revision increases by 1 and the signature binds to the new revision. Audit event `signed.approved` with your comment is written in the same transaction. Approved versions are immutable at the database level.
- **PIN and session**: "Enroll a signature PIN first." without a PIN; "Signature PIN was not accepted." for a wrong PIN (5 consecutive failures lock the PIN for 15 minutes: "Signature PIN is temporarily locked."); "Enter your own signing username and PIN." for a different username; "Session expired. Sign in again before signing." and "Sign in again before signing." for session problems. Failed PIN attempts and identity mismatches are audited even though the approval is refused.
- **Failed submission** returns status 422 with the form and an error summary; entries other than the PIN are kept.

## Related pages

- The specification version.
- [Signature PIN](/signature-pin/)
- [Audit trail](/audit/)
