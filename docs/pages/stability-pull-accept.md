---
title: Accept pull
urls: stability:pull_accept
views: stability.views.pull_accept
templates: ops/sign.html
models: stability.Pull, core.ElectronicSignature
reviewed: 2026-11-10
---

## Purpose

Independently review a pull, its evidence and the linked testing outcome, with meaning **reviewed**.

## Who can use it

- Sign-in required. Role: Reviewer.
- A user who is not permitted (wrong role or not independent) sees the reason and no PIN control (403).

## Layout

- A signing dialog (a plain card without JavaScript): record identifier and revision, the meaning, key facts, signer, a link to enrol or change the signature PIN, the form, **Cancel** and the sign button. Opening the page never signs.

## Actions

| Action | Shown when | Who | Result |
|---|---|---|---|
| **Sign and review** | Not denied | Role: Reviewer | Signs with meaning **reviewed**; returns to the record with a confirmation message |
| **Cancel** / Escape | Always | Any | Returns to the record; nothing is signed |

## Fields

| Field | Model field | Type / units | Required | Meaning and use |
|---|---|---|---|---|
| Required tests / Pulled on / Sample / Deviation | — | Display | — | What you are reviewing |
| Signing username | — | Text | Yes | Must equal your own username |
| Reason for signing | `AuditEvent.reason` | Text, max 2000 | Yes | Recorded with the signature |
| Signature PIN | `PINCredential` (checked, never stored) | Masked digits | Yes | Re-entered for every signature; never shown again |
| Expected revision (hidden) | `Pull.revision` | Integer | Yes | Revision shown when the page opened |

## Rules and hidden logic

- **Preconditions**: pulled and study active ("This pull is not awaiting acceptance."); you neither pulled nor documented it ("You cannot accept a pull you pulled or documented.").
- With a linked sample, collected for this pull and not used for another, every required test must have been created after the pull started, be reviewed, conforming and free of open investigations ("Testing is not complete: …"); with external evidence both the external sample and evidence reference are required ("Link a sample or external stability evidence first.").
- **Identity, session and PIN**: you must type your own username and re-enter your signature PIN for every signature; a wrong username, wrong PIN, expired session or locked PIN is refused with an inline message and nothing changes. Failed PIN attempts are counted and audited even though the action is rejected (five failures lock the PIN for 15 minutes).
- **Stale page**: if the record changed after the page opened: "Record changed. Reload and review before signing."
- **Effect**: one transaction applies the change, raises the record revision by 1, writes the audit event `signed.<meaning>` and an immutable signature bound to the new revision.

## Related pages

- Pull record
