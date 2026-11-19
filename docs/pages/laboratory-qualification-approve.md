---
title: Approve qualification
urls: laboratory:qualification_approve
views: laboratory.views.qualification_approve
templates: ops/sign.html
models: laboratory.Qualification, core.ElectronicSignature
reviewed: 2026-11-19
summary: Sign approval of qualification evidence that someone else recorded, so the subject is qualified for the activity between the stated dates. Quality role only.
---

## Common tasks
### Approve the qualification
1. Check [[Subject]], [[Activity]], [[Qualified for]], [[Valid]], [[Evidence]] and [[Training relied on]] against the controlled record.
2. Enter [[Signing username]], [[Reason for signing]] and [[Signature PIN]].
3. Select [[Sign and approve]]. The qualification record opens.
### Leave without signing
1. Select [[Cancel]]. If the page says you cannot sign, select [[Back to record]]. Nothing is signed.
## Good to know
- Your signature covers the training records the evidence relies on, listed under Training relied on.
- The person who recorded the evidence, the qualified person and whoever recorded a training record it relies on cannot approve it, whatever roles they hold.
- Evidence whose last valid day has passed cannot be approved.
- It qualifies from your signature time, not earlier, and only within its dates.
- Re-enter your PIN for every signature. Five wrong PINs in a row lock it for 15 minutes, even though the action is refused.

## Purpose

Approve qualification evidence with meaning **approved**, making the subject eligible for the activity within the stated dates.

## Who can use it

- Sign-in required. Role: Quality.
- Other roles receive the standard 403 page.
- A Quality user who recorded the evidence or is the qualified person sees "The recorder and the qualified person cannot approve this qualification."; one who recorded a training record the evidence relies on sees "You recorded training this qualification relies on; another quality person approves it."; a record that is not awaiting approval shows "This qualification is approved." (or revoked). Both show the facts, no PIN control, and a **Back to record** link (403).
- An account holding only the Admin role is refused (403) when it opens or submits this page. Admin plus a role listed here has exactly that role's authority, and independence rules (no self-review) still apply.

## Layout

- Breadcrumbs, then a signing dialog (a plain card without JavaScript): QUAL-n and revision, the meaning, key facts, signer, the link **Enroll or change your signature PIN**, the form, **Cancel** and the sign button. Opening the page never signs.

## Actions

| Action | Shown when | Who | Result |
|---|---|---|---|
| **Sign and approve** | Not denied | Role: Quality | Signs with meaning **approved**; returns to the record with a confirmation message |
| **Cancel** / Escape | Always | Any | Returns to the record; nothing is signed |

## Fields

| Field | Model field | Type / units | Required | Meaning and use |
|---|---|---|---|---|
| Subject / Activity / Qualified for / Valid / Evidence / Training relied on | `Qualification.user` or `.equipment`, `.activity`, `.work`, `.valid_from`, `.valid_until`, `.evidence_ref`, `.training` | Display | — | From the qualification record; Qualified for is Performing the work, Reviewing results or Intended use; Valid reads "start to end"; Training relied on lists TRN-n numbers, or "None cited" |
| Signing username | — | Text | Yes | Must equal your own username |
| Reason for signing | `AuditEvent.reason` | Text, max 2000 | Yes | Recorded with the signature |
| Signature PIN | `PINCredential` (checked, never stored) | Masked digits | Yes | Re-entered for every signature; never shown again |
| Expected revision (hidden) | `Qualification.revision` | Integer | Yes | Revision shown when the page opened |

## Rules and hidden logic

- **Preconditions**: awaiting approval; you are neither the recorder nor the qualified person ("The recorder and the qualified person cannot approve this qualification."); you recorded none of the training records it relies on ("You recorded training this qualification relies on; another quality person approves it."); not already expired ("The qualification has already expired."); each cited training record is checked again under lock when you sign: "TRN-n is the training of another person.", "TRN-n is training in “<activity>”, not this activity.", "TRN-n is not acknowledged by the trainee yet." or "TRN-n found the trainee not yet competent."
- Meaning text: "You approve this evidence as showing the subject is qualified for the activity between the stated dates." Success message: "Qualification approved."
- Eligibility starts at the signature time, not before Valid from, and ends after the last valid day (inclusive).
- **Identity, session and PIN**: you must type your own username and re-enter your signature PIN for every signature; a wrong username, wrong PIN, expired session or locked PIN is refused with an inline message and nothing changes. Failed PIN attempts are counted and audited even though the action is rejected (five failures lock the PIN for 15 minutes).
- **Stale page**: if the record changed after the page opened: "Record changed. Reload and review before signing."
- **Effect**: one transaction applies the change, raises the record revision by 1, writes the audit event `signed.<meaning>` and an immutable signature bound to the new revision.

## Related pages

- Qualification record (Cancel returns here)
