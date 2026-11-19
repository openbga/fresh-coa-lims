---
title: Revoke qualification
urls: laboratory:qualification_revoke
views: laboratory.views.qualification_revoke
templates: ops/sign.html
models: laboratory.Qualification, core.ElectronicSignature
reviewed: 2026-11-19
summary: Sign the withdrawal of an approved qualification. Work after your signature time is blocked; work recorded before it stays on record. Quality role only.
---

## Common tasks
### Revoke the qualification
1. Check [[Subject]], [[Activity]], [[Qualified for]], [[Valid]], [[Evidence]] and [[Training relied on]].
2. Enter [[Signing username]], [[Reason for signing]] and [[Signature PIN]].
3. Select [[Sign and revoke]]. The qualification record opens showing Revoked.
### Leave without signing
1. Select [[Cancel]]. If the page says you cannot sign, select [[Back to record]]. Nothing is signed.
## Good to know
- You cannot revoke your own qualification. The person who recorded it may revoke it.
- Revocation is final. Record new evidence to qualify the subject again.
- Approved evidence can be revoked even after its last valid day.
- For equipment, revocation removes its qualification from the signature time, which can make it unfit for use.
- Re-enter your PIN for every signature. Five wrong PINs in a row lock it for 15 minutes, even though the action is refused.

## Purpose

Withdraw an approved qualification with meaning **revoked**. Work after the signature time is blocked; earlier work keeps its evidence.

## Who can use it

- Sign-in required. Role: Quality.
- Other roles receive the standard 403 page.
- A Quality user who is the qualified person sees "You cannot revoke your own qualification."; a record that is not approved shows "This qualification is awaiting approval." or "... is revoked.". Both show the facts, no PIN control, and a **Back to record** link (403). The recorder may revoke.
- An account holding only the Admin role is refused (403) when it opens or submits this page. Admin plus a role listed here has exactly that role's authority, and independence rules (no self-review) still apply.

## Layout

- Breadcrumbs, then a signing dialog (a plain card without JavaScript): QUAL-n and revision, the meaning, key facts, signer, the link **Enroll or change your signature PIN**, the form, **Cancel** and the sign button. Opening the page never signs.

## Actions

| Action | Shown when | Who | Result |
|---|---|---|---|
| **Sign and revoke** | Not denied | Role: Quality | Signs with meaning **revoked**; returns to the record with a confirmation message |
| **Cancel** / Escape | Always | Any | Returns to the record; nothing is signed |

## Fields

| Field | Model field | Type / units | Required | Meaning and use |
|---|---|---|---|---|
| Subject / Activity / Qualified for / Valid / Evidence / Training relied on | `Qualification.user` or `.equipment`, `.activity`, `.work`, `.valid_from`, `.valid_until`, `.evidence_ref`, `.training` | Display | — | From the qualification record; Qualified for is Performing the work, Reviewing results, Release decisions, Issuing certificates or Intended use; Training relied on lists TRN-n numbers, or "None cited" |
| Signing username | — | Text | Yes | Must equal your own username |
| Reason for signing | `AuditEvent.reason` | Text, max 2000 | Yes | Recorded with the signature |
| Signature PIN | `PINCredential` (checked, never stored) | Masked digits | Yes | Re-entered for every signature; never shown again |
| Expected revision (hidden) | `Qualification.revision` | Integer | Yes | Revision shown when the page opened |

## Rules and hidden logic

- **Preconditions**: currently approved ("Only approved qualifications can be revoked."); you are not the subject ("You cannot revoke your own qualification.").
- Revoking never changes a decision already signed under the qualification; it only stops later decisions from relying on it.
- Meaning text: "You withdraw this qualification; work after the signature time is blocked." Success message: "Qualification revoked."
- Revoking a qualification to review results stops that person reviewing or returning results of methods that ask for qualified reviewers, from the signature time; a review already signed keeps the qualification it relied on.
- An approved record can be revoked even after its last valid day.
- Revoked qualifications are immutable and cannot be re-approved; record new evidence. For equipment qualification, revocation removes the equipment's qualification evidence from the signature time.
- **Identity, session and PIN**: you must type your own username and re-enter your signature PIN for every signature; a wrong username, wrong PIN, expired session or locked PIN is refused with an inline message and nothing changes. Failed PIN attempts are counted and audited even though the action is rejected (five failures lock the PIN for 15 minutes).
- **Stale page**: if the record changed after the page opened: "Record changed. Reload and review before signing."
- **Effect**: one transaction applies the change, raises the record revision by 1, writes the audit event `signed.<meaning>` and an immutable signature bound to the new revision.

## Related pages

- Qualification record (Cancel returns here)
