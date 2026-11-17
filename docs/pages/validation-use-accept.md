---
title: Accept intended use
urls: validation:use_accept
views: validation.views.use_accept
templates: ops/sign.html
models: validation.UseAcceptance, core.ElectronicSignature, core.AuditEvent
reviewed: 2026-11-17
summary: Sign the acceptance of the system for the intended use described. Your signature freezes the supported assays, the approved configuration in force and the running release.
---

## Common tasks
### Accept the intended use
1. Review the facts, including [[Approved configuration in force]], [[Running release]] and [[Supersedes]].
2. Enter your [[Signing username]], a [[Reason for signing]] and your [[Signature PIN]].
3. Select [[Sign and accept]]. The record becomes Accepted, and any earlier acceptance is superseded.
### Leave without signing
1. Select [[Cancel]]. Nothing is signed.
### Set up your signature PIN
1. Select [[Enroll or change your signature PIN]] if you have no PIN yet.
## Good to know
- You cannot accept a record you recorded, even with the quality role. The page says why and shows no PIN entry.
- If the approved configuration, the running release or the current acceptance changed after the page opened, signing is refused. Reload and review again.
- A supported assay with no approved version in force now blocks acceptance. Withdraw the record and record the intended use again.
- The acceptance holds no work and releases nothing.

## Purpose

Accept the system for the intended use described, with meaning **accepted**. The signature freezes the supported assays' versions, the approved configuration in force and the running release, so later changes can be shown against them.

## Who can use it

- Sign-in required. Role: Quality. Others, including an account holding only the Admin role, receive 403.
- The Quality user who recorded the record sees "You cannot accept a validation record you recorded."; a record that is not awaiting acceptance shows "This record is <state>; only a record awaiting acceptance can be accepted or withdrawn."; a supported assay without a version in force shows "<codes> has no approved version in force. Withdraw this record and record the intended use again.". Each shows the facts, no PIN control and **Back to record** (403).
- A record whose process owner or system owner is no longer an active account with a working role shows "The process owner named is no longer an active account with a working role. Withdraw this record and record the intended use again." (or "system owner"), with no PIN entry; the signature repeats this check.

## Layout

- Breadcrumbs (Validation, UA-n, Accept) and a signing dialog (a plain card without JavaScript): UA-n and revision, the meaning, the facts, signer, the link **Enroll or change your signature PIN**, the form, **Cancel** and **Sign and accept**. Opening the page never signs.
- Facts: Title, Intended use, Outside the intended use, Supported assays ("title (code vN)"), Methods in force that are not supported assays, Process owner, System owner, Other responsibilities, Validation report, Validation report link, Known issues and conditions, Approved configuration in force (listed by kind as "code vN"), Running release, Supersedes, Recorded by.

## Actions

| Action | Shown when | Who | Result |
|---|---|---|---|
| **Sign and accept** | Not denied | Quality, not the recorder | Signs; shows "UA-n accepted." and returns to the record |
| **Cancel** / Escape | Always | Any | Returns to the record; nothing is signed |

## Fields

| Field | Model field | Type / units | Required | Meaning and use |
|---|---|---|---|---|
| Facts above | `UseAcceptance` fields | Display | — | What the signature binds |
| Signing username | — | Text | Yes | Must equal your own username |
| Reason for signing | `AuditEvent.reason` | Text, max 2000 | Yes | Recorded with the signature |
| Signature PIN | `PINCredential` (checked, never stored) | Masked digits | Yes | Help: "Re-enter your PIN for every signature." |
| Expected revision (hidden) | `UseAcceptance.revision` | Integer | Yes | Revision shown when the page opened |
| Token (hidden) | — | Text, SHA-256 | Yes | Fingerprint of what you reviewed (see Rules) |

## Rules and hidden logic

- Meaning text: "You accept the system for the intended use described, with the supported assays, the approved configuration in force and the running release listed here, on the evidence of the validation report named. Your signature freezes them."
- **What the signature freezes**: the approved versions in force at the signing time of rule sets, specifications, methods, sampling plans and stability protocols; the version of each supported assay; and the running release (`SOURCE_REVISION`, else `RENDER_GIT_COMMIT`, else empty, shown as "Not stated by the deployment"). A SHA-256 of the frozen record is kept.
- **Stale page**: the hidden token covers the configuration, the release, the supported assays and the acceptance that would be superseded. If any changed after the page opened, the signature is refused: "The approved configuration, the running release or the current acceptance changed since this page was opened. Review them again before signing." Reload and review again. A changed revision gives "Record changed. Reload and review before signing."
- **Supersession**: the record accepted before, if any, becomes Superseded by this one in the same transaction, with its own audit event. Acceptances serialize, so exactly one record is accepted afterwards.
- **Identity, session and PIN**: you must type your own username and re-enter your PIN for every signature; a wrong username, wrong PIN, expired session or locked PIN is refused with an inline message and nothing changes. Failed PIN attempts are counted and audited even though the action is rejected.
- **Effect**: one transaction sets the state to Accepted with the signing time, freezes the configuration, raises the revision, supersedes the earlier acceptance, writes the audit events `signed.accepted` (this record) and `use_acceptance.superseded` (the earlier one, reason "Superseded by UA-n." followed by yours), and stores an immutable signature. The database accepts the frozen content only together with the change of state and never lets it change afterwards.
- **No work is held**: the acceptance blocks nothing and releases nothing. Not enforced by this page: whether a later change needs a new acceptance; the laboratory assesses that under its own change control.
- **Assumption**: two different Quality users, one recording and one accepting, is a design default of this product, not a statement of what any regulation requires.

## Related pages

- Intended use record (Cancel returns here)
- [Signature PIN](/signature-pin/)
