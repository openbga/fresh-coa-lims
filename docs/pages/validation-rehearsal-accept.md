---
title: Accept rehearsal
urls: validation:rehearsal_accept
views: validation.views.rehearsal_accept
templates: ops/sign.html
models: validation.Rehearsal, core.ElectronicSignature, core.AuditEvent
reviewed: 2026-11-17
---

## Purpose

Accept a rehearsal record with meaning **accepted**: you confirm it as a true account of the rehearsal, with the outcome it states and the evidence attached. The signature does not make the criteria met.

## Who can use it

- Sign-in required. Role: Quality. Others, including Admin without the Quality role, receive 403.
- The recorder, even holding the Quality role, sees "You cannot accept a validation record you recorded."
- A rehearsal that is not awaiting acceptance shows "This rehearsal is <state>; only a rehearsal awaiting acceptance can be accepted or withdrawn."; one without a file shows "Attach the evidence of the rehearsal before it is accepted.". Each shows the facts, no PIN control and **Back to record** (403).

## Layout

- Breadcrumbs (Validation, Rehearsals, RH-n, Accept) and a signing dialog (a plain card without JavaScript): RH-n and revision, the meaning, the facts, signer, a link to enrol or change the signature PIN, the form, **Cancel** and **Sign and accept**. Opening the page never signs.
- Facts: Rehearsal of, Title, Performed, Release before (upgrade), Release, Environment, Procedure, Acceptance criteria, Outcome, Observations, Issues and actions, Recorded by, Evidence files (name, description and SHA-256 of each).

## Actions

| Action | Shown when | Who | Result |
|---|---|---|---|
| **Sign and accept** | Not denied | Quality, not the recorder | Signs; shows "RH-n accepted." and returns to the rehearsal |
| **Cancel** / Escape | Always | Any | Returns to the rehearsal; nothing is signed |

## Fields

| Field | Model field | Type / units | Required | Meaning and use |
|---|---|---|---|---|
| Facts above | `Rehearsal` and `RehearsalFile` fields | Display | — | What you confirm |
| Signing username | — | Text | Yes | Must equal your own username |
| Reason for signing | `AuditEvent.reason` | Text, max 2000 | Yes | Recorded with the signature |
| Signature PIN | `PINCredential` (checked, never stored) | Masked digits | Yes | Help: "Re-enter your PIN for every signature." |
| Expected revision (hidden) | `Rehearsal.revision` | Integer | Yes | Revision shown when the page opened |

## Rules and hidden logic

- Meaning text: "You accept this record as a true account of the rehearsal, with the outcome it states and the evidence attached."
- **Stale page**: the revision rises with every attached file and every state change. A page opened before a file was attached is refused: "Record changed. Reload and review before signing."
- **Identity, session and PIN**: you must type your own username and re-enter your PIN for every signature; a wrong username, wrong PIN, expired session or locked PIN is refused with an inline message and nothing changes. Failed PIN attempts are counted and audited even though the action is rejected.
- **Effect**: one transaction sets the state to Accepted with the signing time, raises the revision, writes the audit event `signed.accepted` and stores an immutable signature bound to the new revision. The database allows the accepted state only with its acceptance time.
- An accepted rehearsal whose outcome is "Criteria not met" is accepted as a true record and shows as "Accepted: criteria not met".
- Nothing is held or released by this acceptance.
- **Assumption**: two different people, one recording and one accepting, is a design default of this product, not a statement of what any regulation requires.

## Related pages

- Rehearsal record (Cancel returns here)
- [Signature PIN](/signature-pin/)
