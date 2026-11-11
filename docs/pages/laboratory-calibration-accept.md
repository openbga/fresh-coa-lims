---
title: Accept calibration
urls: laboratory:calibration_accept
views: laboratory.views.calibration_accept
templates: ops/sign.html
models: laboratory.Calibration, core.ElectronicSignature
reviewed: 2026-11-11
---

## Purpose

Independently review calibration evidence and accept its outcome with meaning **reviewed**.

## Who can use it

- Sign-in required. Role: Reviewer.
- Without the Reviewer role you receive the standard 403 page.
- A Reviewer who recorded the calibration ("You recorded this calibration, so you cannot accept it.") or opens one already accepted ("This calibration has already been accepted.") sees that reason, the facts and a **Back to record** link, with no PIN control (403). The recorder check comes first.
- An account holding only the Admin role is refused (403) when it opens or submits this page. Admin plus a role listed here has exactly that role's authority, and independence rules (no self-review) still apply.

## Layout

- Breadcrumbs (Laboratory, Equipment, the asset, Accept calibration), then a signing dialog (a plain card without JavaScript): the record ("ASSET calibration N") and revision, the meaning, key facts, signer, a link to enrol or change the signature PIN, the form, **Cancel** and the sign button. Opening the page never signs.

## Actions

| Action | Shown when | Who | Result |
|---|---|---|---|
| **Sign and review** | Not denied | Role: Reviewer | Signs with meaning **reviewed**; returns to the record with a confirmation message |
| **Cancel** / Escape | Always | Any | Returns to the record; nothing is signed |

## Fields

| Field | Model field | Type / units | Required | Meaning and use |
|---|---|---|---|---|
| Performed / Due (inclusive) / Outcome | `Calibration.performed_at`, `.due_date`, `.outcome` | Display | — | From the calibration record |
| Reference standard / Tolerance note | `Calibration.standard_ref`, `.tolerance_note` | Display | — | Evidence you are reviewing |
| Recorded by | — | Display | — | The person who recorded it |
| Signing username | — | Text | Yes | Must equal your own username |
| Reason for signing | `AuditEvent.reason` | Text, max 2000 | Yes | Recorded with the signature |
| Signature PIN | `PINCredential` (checked, never stored) | Masked digits | Yes | Re-entered for every signature; never shown again |
| Expected revision (hidden) | `Calibration.revision` | Integer | Yes | Revision shown when the page opened |

## Rules and hidden logic

- **Preconditions**: still awaiting acceptance ("This calibration has already been accepted."); you did not record it ("You cannot accept a calibration you recorded."), even if you also hold other roles.
- Accepting a passing calibration makes it count for fitness from the acceptance time; accepting a failure confirms it (a failure already counted when recorded). Accepted calibrations are immutable.
- **Meaning text**: "You reviewed the calibration evidence and accept the outcome shown." Success message: "Calibration accepted."
- **Identity, session and PIN**: you must type your own username and re-enter your signature PIN for every signature; a wrong username, wrong PIN, expired session or locked PIN is refused with an inline message and nothing changes. Failed PIN attempts are counted and audited even though the action is rejected (five failures lock the PIN for 15 minutes).
- **Stale page**: if the record changed after the page opened: "Record changed. Reload and review before signing."
- **Effect**: one transaction applies the change, raises the record revision by 1, writes the audit event `signed.<meaning>` and an immutable signature bound to the new revision.

## Related pages

- Equipment record
- [Calibrations](/laboratory/calibrations/)
