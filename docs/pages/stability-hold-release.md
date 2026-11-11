---
title: Release hold
urls: stability:hold_release
views: stability.views.hold_release
templates: ops/sign.html
models: stability.Hold, core.ElectronicSignature
reviewed: 2026-11-10
---

## Purpose

Approve releasing a hold with meaning **approved**. Other holds and retention obligations continue to apply.

## Who can use it

- Sign-in required. Role: Quality.
- A user who is not permitted sees the reason and no PIN control (403): "You placed this hold, so you cannot release it." (checked first) or "This hold is already released."
- Other roles are refused by role (403).
- An account holding only the Admin role is refused (403) when it opens or submits this page. Admin plus a role listed here has exactly that role's authority, and independence rules (no self-review) still apply.

## Layout

- Title "Release HOLD-n". A signing dialog (a plain card without JavaScript): record identifier and revision, the meaning, key facts, signer, a link to enrol or change the signature PIN, the form, **Cancel** and the sign button. Opening the page never signs.

## Actions

| Action | Shown when | Who | Result |
|---|---|---|---|
| **Sign and approve** | Not denied | Role: Quality | Signs with meaning **approved**; returns to the record with a confirmation message |
| **Cancel** / Escape | Always | Any | Returns to the record; nothing is signed |

## Fields

| Field | Model field | Type / units | Required | Meaning and use |
|---|---|---|---|---|
| Lot / Kind / Reason / Reference | — | Display | — | The hold being released |
| Signing username | — | Text | Yes | Must equal your own username |
| Reason for signing | `AuditEvent.reason` | Text, max 2000 | Yes | Recorded with the signature |
| Signature PIN | `PINCredential` (checked, never stored) | Masked digits | Yes | Re-entered for every signature; never shown again |
| Expected revision (hidden) | `Hold.revision` | Integer | Yes | Revision shown when the page opened |

## Rules and hidden logic

- **Preconditions**: still active ("This hold is already released."); you did not place it ("The person who placed a hold cannot release it.").
- Released holds are immutable; place a new hold if needed. Release also raises the lot revision while the lot is in quarantine, so a disposition dialog opened earlier goes stale.
- Meaning text: "You approve releasing this hold. Other holds and retention obligations continue to apply." Button: **Sign and approve**; success message "Hold released."
- **Identity, session and PIN**: you must type your own username and re-enter your signature PIN for every signature; a wrong username, wrong PIN, expired session or locked PIN is refused with an inline message and nothing changes. Failed PIN attempts are counted and audited even though the action is rejected (five failures lock the PIN for 15 minutes).
- **Stale page**: if the record changed after the page opened: "Record changed. Reload and review before signing."
- **Effect**: one transaction applies the change, raises the record revision by 1, writes the audit event `signed.<meaning>` and an immutable signature bound to the new revision.

## Related pages

- Hold record (plain name: opened from [Holds](/stability/holds/))
