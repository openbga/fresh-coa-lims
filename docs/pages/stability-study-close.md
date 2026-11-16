---
title: Close study
urls: stability:study_close
views: stability.views.study_close
templates: ops/sign.html
models: stability.Study, core.ElectronicSignature
reviewed: 2026-11-15
---

## Purpose

Approve closing a study as completed or terminated, with meaning **approved**.

## Who can use it

- Sign-in required. Role: Quality; other roles receive 403.
- A Quality user who started the study sees "You started this study, so you cannot close it.", for an already closed study "This study is already closed.", and while testing of the study's pulls is in progress "Testing of the study's pulls is in progress; finish it first: …" with each reason; no PIN control is shown (403).
- An account holding only the Admin role is refused (403) when it opens or submits this page. Admin plus a role listed here has exactly that role's authority, and independence rules (no self-review) still apply.

## Layout

- A signing dialog (a plain card without JavaScript): record identifier and revision, the meaning, key facts, signer, a link to enrol or change the signature PIN, the form, **Cancel** and the sign button. Opening the page never signs.

## Actions

| Action | Shown when | Who | Result |
|---|---|---|---|
| **Sign and approve** | Not denied | Role: Quality | Signs with meaning **approved**; returns to the study record with "Study closed." |
| **Cancel** / Escape | Always | Any | Returns to the record; nothing is signed |

## Fields

| Field | Model field | Type / units | Required | Meaning and use |
|---|---|---|---|---|
| Lot / Protocol / Open pulls | — | Display | — | Context for the decision |
| Outcome | `Study.state` | Choice: "Completed: every pull accepted or missed" or "Terminated early" | Yes | Becomes the study's state |
| Signing username | — | Text | Yes | Must equal your own username |
| Reason for signing | `AuditEvent.reason` | Text, max 2000 | Yes | Recorded with the signature |
| Signature PIN | `PINCredential` (checked, never stored) | Masked digits | Yes | Re-entered for every signature; never shown again |
| Expected revision (hidden) | `Study.revision` | Integer | Yes | Revision shown when the page opened |

## Rules and hidden logic

- **Preconditions**: still active ("This study is already closed."); you did not start it ("The person who started a study cannot close it."); completion with open pulls is refused ("N pull(s) are not accepted or missed; terminate instead or finish them.").
- **Testing in progress** blocks closing, as completed or terminated, with "Testing of the study's pulls is in progress; finish it first: …" (also checked when signing). Reasons: a test of one of its pulls awaits independent review ("<test> <code> awaits independent review."); an open test already holds an observation, raw-data file or QC batch ("<test> <code> holds results, raw data or a QC batch that were not submitted."); or an investigation of one of its tests is open ("<investigation> is open: <trigger>."). An open test that holds nothing does not stop closing and is left as it is.
- Meaning text adds: a closed study's pulls take no more testing, and open tests that hold nothing are left as they are.
- A closed study and its pulls are immutable. Closing sets the state and the closed time.
- Open pulls means Scheduled or Pulled pulls; the page shows their count. Accepted and Missed pulls do not count.
- **Identity, session and PIN**: you must type your own username and re-enter your signature PIN for every signature; a wrong username, wrong PIN, expired session or locked PIN is refused with an inline message and nothing changes. Failed PIN attempts are counted and audited even though the action is rejected (five failures lock the PIN for 15 minutes).
- **Stale page**: if the record changed after the page opened: "Record changed. Reload and review before signing."
- **Effect**: one transaction applies the change, raises the record revision by 1, writes the audit event `signed.<meaning>` and an immutable signature bound to the new revision.

## Related pages

- Study record (Cancel and success)
