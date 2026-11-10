---
title: Close study
urls: stability:study_close
views: stability.views.study_close
templates: ops/sign.html
models: stability.Study, core.ElectronicSignature
reviewed: 2026-11-10
---

## Purpose

Approve closing a study as completed or terminated, with meaning **approved**.

## Who can use it

- Sign-in required. Role: Quality.
- A user who is not permitted (wrong role or not independent) sees the reason and no PIN control (403).

## Layout

- A signing dialog (a plain card without JavaScript): record identifier and revision, the meaning, key facts, signer, a link to enrol or change the signature PIN, the form, **Cancel** and the sign button. Opening the page never signs.

## Actions

| Action | Shown when | Who | Result |
|---|---|---|---|
| **Sign and approve** | Not denied | Role: Quality | Signs with meaning **approved**; returns to the record with a confirmation message |
| **Cancel** / Escape | Always | Any | Returns to the record; nothing is signed |

## Fields

| Field | Model field | Type / units | Required | Meaning and use |
|---|---|---|---|---|
| Lot / Protocol / Open pulls | — | Display | — | Context for the decision |
| Outcome (form) | — | Display | — | Completed needs every pull accepted or missed; Terminated closes early |
| Signing username | — | Text | Yes | Must equal your own username |
| Reason for signing | `AuditEvent.reason` | Text, max 2000 | Yes | Recorded with the signature |
| Signature PIN | `PINCredential` (checked, never stored) | Masked digits | Yes | Re-entered for every signature; never shown again |
| Expected revision (hidden) | `Study.revision` | Integer | Yes | Revision shown when the page opened |

## Rules and hidden logic

- **Preconditions**: still active ("This study is already closed."); you did not start it ("The person who started a study cannot close it."); completion with open pulls is refused ("N pull(s) are not accepted or missed; terminate instead or finish them.").
- A closed study and its pulls are immutable.
- **Identity, session and PIN**: you must type your own username and re-enter your signature PIN for every signature; a wrong username, wrong PIN, expired session or locked PIN is refused with an inline message and nothing changes. Failed PIN attempts are counted and audited even though the action is rejected (five failures lock the PIN for 15 minutes).
- **Stale page**: if the record changed after the page opened: "Record changed. Reload and review before signing."
- **Effect**: one transaction applies the change, raises the record revision by 1, writes the audit event `signed.<meaning>` and an immutable signature bound to the new revision.

## Related pages

- Study record
