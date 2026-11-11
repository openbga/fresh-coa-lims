---
title: Accept pull
urls: stability:pull_accept
views: stability.views.pull_accept
templates: ops/sign.html
models: stability.Pull, core.ElectronicSignature
reviewed: 2026-11-11
---

## Purpose

Independently review a pull, its evidence and the linked testing outcome, with meaning **reviewed**.

## Who can use it

- Sign-in required. Role: Reviewer.
- Other roles receive 403. A Reviewer who is not permitted sees the reason and no PIN control (403): "You pulled or documented this pull, so you cannot accept it." (checked first) or "This pull is not awaiting acceptance."
- An account holding only the Admin role is refused (403) when it opens or submits this page. Admin plus a role listed here has exactly that role's authority, and independence rules (no self-review) still apply.

## Layout

- Title "Accept pull · <timepoint>". A signing dialog (a plain card without JavaScript): record identifier and revision, the meaning, key facts, signer, a link to enrol or change the signature PIN, the form, **Cancel** and the sign button. Opening the page never signs.

## Actions

| Action | Shown when | Who | Result |
|---|---|---|---|
| **Sign and review** | Not denied | Role: Reviewer | Signs with meaning **reviewed**; returns to the record with a confirmation message |
| **Cancel** / Escape | Always | Any | Returns to the record; nothing is signed |

## Fields

| Field | Model field | Type / units | Required | Meaning and use |
|---|---|---|---|---|
| Required tests / Pulled on / Sample / Deviation | — | Display (the sample shows its reference, or the external sample ID) | — | What you are reviewing |
| Signing username | — | Text | Yes | Must equal your own username |
| Reason for signing | `AuditEvent.reason` | Text, max 2000 | Yes | Recorded with the signature |
| Signature PIN | `PINCredential` (checked, never stored) | Masked digits | Yes | Re-entered for every signature; never shown again |
| Expected revision (hidden) | `Pull.revision` | Integer | Yes | Revision shown when the page opened |

## Rules and hidden logic

- **Preconditions**: pulled and study active ("This pull is not awaiting acceptance."); you neither pulled nor documented it ("You cannot accept a pull you pulled or documented.").
- With a linked sample: it must have been collected on the pull date, not in the future, and not be evidence for another pull. Each required test code needs a reviewed, conforming analytical test created on or after the pull date (tests created earlier are ignored and reported). Any open investigation, or one that confirmed an out-of-specification result, blocks acceptance; a test that was under investigation counts only if the investigation was invalidated ("Testing is not complete: …" lists the reasons); with external evidence both the external sample and evidence reference are required ("Link a sample or external stability evidence first.").
- **Identity, session and PIN**: you must type your own username and re-enter your signature PIN for every signature; a wrong username, wrong PIN, expired session or locked PIN is refused with an inline message and nothing changes. Failed PIN attempts are counted and audited even though the action is rejected (five failures lock the PIN for 15 minutes).
- **Stale page**: if the record changed after the page opened: "Record changed. Reload and review before signing."
- Meaning text: "You reviewed the pull, its evidence and the linked testing outcome." Button **Sign and review**; success message "Pull accepted."; the pull becomes Accepted with its acceptance time.
- **Effect**: one transaction applies the change, raises the record revision by 1, writes the audit event `signed.<meaning>` and an immutable signature bound to the new revision.

## Related pages

- Pull record (plain name: opened from [Stability pulls](/stability/pulls/))
