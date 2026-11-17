---
title: Approve protocol
urls: stability:protocol_approve
views: stability.views.protocol_approve
templates: ops/sign.html
models: stability.Protocol, core.ElectronicSignature
reviewed: 2026-11-17
summary: Sign the approval of a complete draft protocol: its conditions, timepoints, tests and named specification. Quality users only, and never the protocol's author.
---

## Common tasks
### Approve the protocol
1. Check [[Conditions]], [[Timepoints]] and [[Acceptance criteria]] in the summary.
2. Enter your [[Signing username]], a [[Reason for signing]] and your [[Signature PIN]].
3. Select [[Sign and approve]]. Earlier approved versions of this code become Superseded.
### Set up your signature PIN
1. Select [[Enroll or change your signature PIN]] if you have no PIN yet.
### Leave without signing
1. Select [[Cancel]]. Nothing is signed.
## Good to know
- You cannot approve a protocol you authored, even with the quality role.
- When the protocol names a specification, approval is refused until the version in force states every test, with a method in force.
- If the protocol changed after you opened this page, signing is refused. Reload and review it first.
- New studies start only on the current approved version. Studies already started on an earlier version are not changed.

## Purpose

Approve the complete protocol (conditions, timepoints, tests) with meaning **approved**; earlier approved versions of the code become Superseded.

## Who can use it

- Sign-in required. Role: Quality.
- Other roles receive 403. A Quality user who is not permitted sees the reason and no PIN control (403): "You authored this protocol, so you cannot approve it." (checked first) "Only a draft protocol can be approved.", or, when the protocol names a specification that cannot state every test, the reasons for each such test (see Rules).
- An account holding only the Admin role is refused (403) when it opens or submits this page. Admin plus a role listed here has exactly that role's authority, and independence rules (no self-review) still apply.

## Layout

- Title "Approve <code> v<n>". A signing dialog (a plain card without JavaScript): record identifier and revision, the meaning, key facts, signer, a link to enrol or change the signature PIN, the form, **Cancel** and the sign button. Opening the page never signs.

## Actions

| Action | Shown when | Who | Result |
|---|---|---|---|
| **Sign and approve** | Not denied | Role: Quality | Signs with meaning **approved**; returns to the record with a confirmation message |
| **Cancel** / Escape | Always | Any | Returns to the record; nothing is signed |

## Fields

| Field | Model field | Type / units | Required | Meaning and use |
|---|---|---|---|---|
| Product / Conditions / Timepoints / Acceptance criteria / Author / Content digest | — | Display (counts; Acceptance criteria shows "<specification code>, v<n> in force now", "<code>, no version in force" or "Not in the system"; first 12 characters of the digest) | — | What you are approving |
| Signing username | — | Text | Yes | Must equal your own username |
| Reason for signing | `AuditEvent.reason` | Text, max 2000 | Yes | Recorded with the signature |
| Signature PIN | `PINCredential` (checked, never stored) | Masked digits | Yes | Re-entered for every signature; never shown again |
| Expected revision (hidden) | `Protocol.revision` | Integer | Yes | Revision shown when the page opened |

## Rules and hidden logic

- **Preconditions**: draft ("Only a draft protocol can be approved."); you are not the author ("The protocol author cannot approve it."); at least one condition ("The protocol has no storage conditions.") each with a timepoint ("Every storage condition needs at least one timepoint."); content unchanged since the digest ("Protocol content changed. Reload and review before signing.").
- **Specification check**: a protocol that names a specification is approved only while the specification's approved version in force states every test of every timepoint with a method in force. Otherwise the page is denied (403, no PIN control), and a sign attempt is refused, with one reason for each test, such as "Specification <code> v<n> does not state <test>. The protocol tests it at <timepoint>.", "Method <method> of <test> has no approved version effective now. …" or "Specification <code> has no approved version effective now." A protocol with no specification is not checked.
- Meaning text: "You approve the complete protocol: its conditions, timepoints and tests, and the specification that states their acceptance criteria where one is named. Earlier approved versions of this code are superseded." Success message "Protocol approved."; returns to the protocol record, which records the approval time.
- Approving sets state Approved, then every earlier Approved version of the same code becomes Superseded (done under a lock so two approvals cannot both stay current). Superseded versions get event `protocol.superseded`; their studies continue, but new studies need the current approved version.
- **Identity, session and PIN**: you must type your own username and re-enter your signature PIN for every signature; a wrong username, wrong PIN, expired session or locked PIN is refused with an inline message and nothing changes. Failed PIN attempts are counted and audited even though the action is rejected (five failures lock the PIN for 15 minutes).
- **Stale page**: if the record changed after the page opened: "Record changed. Reload and review before signing."
- **Effect**: one transaction applies the change, raises the record revision by 1, writes the audit event `signed.<meaning>` and an immutable signature bound to the new revision.

## Related pages

- Protocol record (plain name: opened from [Stability protocols](/stability/protocols/))
