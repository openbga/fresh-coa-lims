---
title: Approve qualification
urls: laboratory:qualification_approve
views: laboratory.views.qualification_approve
templates: ops/sign.html
models: laboratory.Qualification, core.ElectronicSignature
reviewed: 2026-11-11
---

## Purpose

Approve qualification evidence with meaning **approved**, making the subject eligible for the activity within the stated dates.

## Who can use it

- Sign-in required. Role: Quality.
- Other roles receive the standard 403 page.
- A Quality user who recorded the evidence or is the qualified person sees "The recorder and the qualified person cannot approve this qualification."; a record that is not awaiting approval shows "This qualification is approved." (or revoked). Both show the facts, no PIN control, and a **Back to record** link (403).
- An account holding only the Admin role is refused (403) when it opens or submits this page. Admin plus a role listed here has exactly that role's authority, and independence rules (no self-review) still apply.

## Layout

- Breadcrumbs, then a signing dialog (a plain card without JavaScript): QUAL-n and revision, the meaning, key facts, signer, a link to enrol or change the signature PIN, the form, **Cancel** and the sign button. Opening the page never signs.

## Actions

| Action | Shown when | Who | Result |
|---|---|---|---|
| **Sign and approve** | Not denied | Role: Quality | Signs with meaning **approved**; returns to the record with a confirmation message |
| **Cancel** / Escape | Always | Any | Returns to the record; nothing is signed |

## Fields

| Field | Model field | Type / units | Required | Meaning and use |
|---|---|---|---|---|
| Subject / Activity / Valid / Evidence | `Qualification.user` or `.equipment`, `.activity`, `.valid_from`, `.valid_until`, `.evidence_ref` | Display | — | From the qualification record; Valid reads "start to end" |
| Signing username | — | Text | Yes | Must equal your own username |
| Reason for signing | `AuditEvent.reason` | Text, max 2000 | Yes | Recorded with the signature |
| Signature PIN | `PINCredential` (checked, never stored) | Masked digits | Yes | Re-entered for every signature; never shown again |
| Expected revision (hidden) | `Qualification.revision` | Integer | Yes | Revision shown when the page opened |

## Rules and hidden logic

- **Preconditions**: awaiting approval; you are neither the recorder nor the qualified person ("The recorder and the qualified person cannot approve this qualification."); not already expired ("The qualification has already expired.").
- Meaning text: "You approve this evidence as showing the subject is qualified for the activity between the stated dates." Success message: "Qualification approved."
- Eligibility starts at the signature time, not before Valid from, and ends after the last valid day (inclusive).
- **Identity, session and PIN**: you must type your own username and re-enter your signature PIN for every signature; a wrong username, wrong PIN, expired session or locked PIN is refused with an inline message and nothing changes. Failed PIN attempts are counted and audited even though the action is rejected (five failures lock the PIN for 15 minutes).
- **Stale page**: if the record changed after the page opened: "Record changed. Reload and review before signing."
- **Effect**: one transaction applies the change, raises the record revision by 1, writes the audit event `signed.<meaning>` and an immutable signature bound to the new revision.

## Related pages

- Qualification record (Cancel returns here)
